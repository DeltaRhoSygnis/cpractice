/**
 * In-memory record of files changed during a session, plus tree/path rendering.
 *
 * Ported from the ECC V1 `plugins/lib/changed-files-store.ts`. The V1 version
 * used module-level state; this factory keeps state scoped to one plugin
 * instance so it is safe to reason about and test.
 */

import * as path from "node:path"

export type ChangeType = "added" | "modified" | "deleted"

export interface TreeNode {
  name: string
  path: string
  changeType?: ChangeType
  children: TreeNode[]
}

export interface ChangeStore {
  recordChange(filePath: string, type: ChangeType): void
  getChanges(): Map<string, ChangeType>
  clearChanges(): void
  buildTree(filter?: ChangeType): TreeNode[]
  getChangedPaths(filter?: ChangeType): Array<{ path: string; changeType: ChangeType }>
  hasChanges(): boolean
}

export function createChangeStore(worktreeRoot: string): ChangeStore {
  const root = worktreeRoot || process.cwd()
  const changes = new Map<string, ChangeType>()

  function toRelative(p: string): string {
    if (!p) return ""
    const normalized = path.normalize(p)
    if (path.isAbsolute(normalized) && root) {
      const rel = path.relative(root, normalized)
      return rel.startsWith("..") ? normalized : rel
    }
    return normalized
  }

  function addToTree(
    children: TreeNode[],
    segs: string[],
    fullPath: string,
    changeType: ChangeType
  ): void {
    if (segs.length === 0) return
    const [head, ...rest] = segs
    let child = children.find((c) => c.name === head)

    if (rest.length === 0) {
      if (child) {
        child.changeType = changeType
        child.path = fullPath
      } else {
        children.push({ name: head, path: fullPath, changeType, children: [] })
      }
      return
    }

    if (!child) {
      const dirPath = segs.slice(0, -rest.length).join(path.sep)
      child = { name: head, path: dirPath, children: [] }
      children.push(child)
    }
    addToTree(child.children, rest, fullPath, changeType)
  }

  return {
    recordChange(filePath, type) {
      const rel = toRelative(filePath)
      if (!rel) return
      changes.set(rel, type)
    },

    getChanges() {
      return new Map(changes)
    },

    clearChanges() {
      changes.clear()
    },

    buildTree(filter) {
      const tree: TreeNode[] = []
      for (const [relPath, changeType] of changes) {
        if (filter && changeType !== filter) continue
        const segs = relPath.split(path.sep).filter(Boolean)
        if (segs.length === 0) continue
        addToTree(tree, segs, relPath, changeType)
      }

      const sortNodes = (nodes: TreeNode[]): TreeNode[] =>
        [...nodes]
          .sort((a, b) => {
            const aIsFile = a.changeType !== undefined
            const bIsFile = b.changeType !== undefined
            if (aIsFile !== bIsFile) return aIsFile ? 1 : -1
            return a.name.localeCompare(b.name)
          })
          .map((n) => ({ ...n, children: sortNodes(n.children) }))

      return sortNodes(tree)
    },

    getChangedPaths(filter) {
      const list: Array<{ path: string; changeType: ChangeType }> = []
      for (const [p, t] of changes) {
        if (filter && t !== filter) continue
        list.push({ path: p, changeType: t })
      }
      list.sort((a, b) => a.path.localeCompare(b.path))
      return list
    },

    hasChanges() {
      return changes.size > 0
    },
  }
}
