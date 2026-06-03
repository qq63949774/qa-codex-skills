# Mathsota Arithmetic Level Rules

## Raw Stage Shape

Mathsota arithmetic stages use the legacy Mixword raw stage shape:

- `column`: board columns containing raw card tokens
- `stock`: draw-pile card tokens
- `key`: category groups
- `className`: retained from the original schema, but arithmetic stages should use text cards

## Token Semantics

For a token such as `8:2x4`:

- `8` is the numeric category / target.
- `2x4` is the card expression.
- The token is valid only when the expression evaluates to the target.

For a token such as `8:8`:

- Treat it as the type/category card for target `8`.
- Do not require `8` to appear in `key[].content`.

## Formula Grammar

Use the same shape accepted by the client:

- left operand: one or more ASCII digits
- operator: one of `+`, `-`, `−`, `*`, `x`, `X`, `×`, `/`, `÷`
- right operand: one or more ASCII digits

Examples:

- `2x4`
- `20/2`
- `12-4`
- `3+5`

Do not accept parentheses, chained operations, decimals, negative operands, or blank expressions unless the client code is updated.

## Evaluation

Evaluate division exactly with rational arithmetic. A result such as `3/2` does not equal integer target `1` or `2`.

## Relationship To Mixword Checks

Run `mixword-level-legality-check` when the user asks about level legality, duplicate/missing cards, cover behavior, or runtime initial state.

Run this skill when the user asks about arithmetic correctness or formula/category matching.
