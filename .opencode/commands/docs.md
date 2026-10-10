---
description: Look up current library documentation via Context7 MCP
---

# Docs Command

Look up current documentation for: $ARGUMENTS

## Process

1. **Identify the Library/Framework**
   - Parse the user's question to determine the target library
   - If ambiguous, ask for clarification

2. **Fetch Documentation**
   - Use Context7 MCP to fetch current docs
   - Focus on the specific API or feature mentioned
   - Include code examples from official docs

3. **Provide Relevant Examples**
   - Show the most common usage patterns
   - Include parameter descriptions
   - Note any version-specific changes

4. **Link to Source**
   - Provide official documentation URL
   - Reference specific sections if applicable

## Output Format

### Library/Topic
[Name and version if available]

### Official Documentation
[URL to official docs]

### Quick Reference
```[language]
// Most common usage
[example code]

// With options/configuration
[example code with options]
```

### Key Points
- [Important point 1]
- [Important point 2]
- [Important point 3]

### Related APIs
- [Related API 1]: [Brief description]
- [Related API 2]: [Brief description]
