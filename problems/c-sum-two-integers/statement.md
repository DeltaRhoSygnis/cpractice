# Sum of Two Integers

## Task

Write a C program that reads two integers from standard input and prints their
sum.

## Input

A single line containing two integers separated by a space, for example:

```
2 3
```

## Output

The sum of the two integers, followed by a newline:

```
5
```

## Constraints

- Each integer is between `-1000000` and `1000000`.
- Read exactly two integers.
- Print exactly the sum, with a single trailing newline.

## Examples

**Example 1**

Input:
```
2 3
```
Output:
```
5
```

**Example 2**

Input:
```
-4 1
```
Output:
```
-3
```

## Notes

Read both numbers before you calculate. Remember that `scanf` needs the address
of each variable (the `&` operator).
