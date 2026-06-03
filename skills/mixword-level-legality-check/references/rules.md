# Mixword Level Legality Rules

Use this reference when the user asks why a level passed or failed, or when the script needs to be extended.

## Raw Stage Shape

Each raw stage contains:

- `column`: visible work columns before adaptation
- `stock`: explicit stock cards
- `key`: category definitions
- `className`: image resource mapping

Normal levels come from `Assets/Game/Levels/Resources/LevelData/<lang>`.
Special levels come from `Assets/Game/Levels/Resources/SpecialLevelData/<lang>`.

## Resource Slot Mapping

The project maps a requested game level to a raw slot by:

1. Sorting file names numerically
2. Treating each file as 10 slots
3. Starting from `(level - 1) % (file_count * 10)`
4. Scanning forward until it finds a valid object slot

This means game levels can wrap and reuse raw resource slots.

## Internal Card Encoding

The adapter converts tokens into float card ids:

- integer `type` means category card
- `type + 0.01`, `type + 0.02`, ... mean word cards in that category

Examples:

- `1` = category card for the first `key` group
- `1.01` = first content item in that group
- `1.02` = second content item in that group

## Adapter Output

The adapter creates:

- `founds`: one empty base pile per raw column
- `columns`: adapted raw columns
- `stocks`: adapted raw stock
- `wordBooks` and `books`: category metadata

## Build-Cover Rule

At runtime, the game does not trust raw `stock` to contain all remaining cards.

It computes the full expected card set from `wordBooks` and `books.count`, then:

1. removes cards already present in base and work
2. removes cards explicitly listed in raw `stock`
3. auto-fills the remaining cards into cover
4. shuffles those auto-filled cards
5. appends the explicit stock cards after the auto-filled portion

So a raw stage may still be legal even when `stock` is incomplete.

## Start State

After `DeskData.init` and `Desk.startGame`:

- base piles are built from `founds`
- work piles are built from `columns`
- all work cards start covered, then only the top card of each non-empty work pile is revealed
- deck has exactly two piles and both start empty
- cover holds the build-cover result

## Move Rules

### Cover to Deck

Clicking cover moves the last two cover cards, one each, into the two deck piles, and reveals them.

### Work Drag

Dragging from a work pile drags the entire uncovered tail, not an arbitrary suffix from the selected card.

### Push to Work

- empty work accepts any dragged uncovered chain
- non-empty work rejects if its top card is a category card
- otherwise the first card in the dragged chain must match the destination top card's category

### Push to Base

- empty base accepts only when the dragged chain ends with a category card
- non-empty base accepts only when the first dragged card matches the base category

### Base Completion

A base completes when its pile length reaches `word_count + 1`:

- one category card
- all words for that category

## Runtime Legality Invariants

Useful invariants for checking a level:

- final multiset across base/work/deck/cover equals the full expected card set
- no duplicate cards
- no missing cards after build-cover
- each non-empty base contains exactly one category and no overflow
- each work pile has covered cards before uncovered cards, never the reverse
- deck piles are stacks only; top card is the last element

## Deadlock Logic

The project only treats a state as fail when:

- cover is empty
- no work pile is empty
- no revealed category card can move into an empty base
- no relevant top/deck card can match another candidate category

This is narrower than "no obvious move at a glance."
