# imixsota Project Map

Use this reference only when the request is about this repository.

## Scope

- Project root: `<IMIXSOTA_REPO>`
- Product: iOS project `WordTop`
- Typical requirement inspection target: ad loading, config parsing, lifecycle, acceptance section verification

## High-value files

### Requirement inputs

- `【imixsota】v1.2.0.docx`

### Ad implementation

- `WordTop/Ad/V2/AdMaxV2Service.swift`
- `WordTop/Ad/V2/AdMaxPlacementLoader.swift`
- `WordTop/Ad/V2/AdMaxDecisionEngine.swift`
- `WordTop/Ad/V2/AdMaxCachePool.swift`
- `WordTop/Ad/V2/AdMaxConfigStore.swift`
- `WordTop/Ad/V2/AdMaxTypes.swift`
- `WordTop/Ad/AdAgent.swift`
- `WordTop/Report/SdkAgent.swift`
- `WordTop/SceneDelegate.swift`

### Existing evidence-heavy tests

- `WordTopTests/AdMaxPlacementLoaderTests.swift`
- `WordTopTests/AdMaxV2ServiceTests.swift`
- `WordTopTests/AdMaxDecisionEngineTests.swift`
- `WordTopTests/AdMaxCachePoolTests.swift`
- `WordTopTests/AdMaxConfigStoreTests.swift`
- `WordTopTests/SdkAgentAdMaxParsingTests.swift`
- `WordTopTests/AdMaxLifecycleConfigTests.swift`

## Evidence strategy

When a requirement is ad-related, try to prove it in this order:

1. Implementation path exists in `WordTop/Ad/V2/` or related lifecycle/config files
2. Existing tests constrain the behavior
3. Runtime execution succeeds locally

If step 3 is unavailable, say so explicitly.

## Known runtime verification preconditions

For local iOS test execution, check these first:

- Full Xcode toolchain is available
- Simulator service is available
- `Pods/Target Support Files/...` exists
- CocoaPods can be executed if Pods are missing

If these preconditions fail, runtime acceptance is blocked even when static evidence is strong.

## Known requirement-risk patterns

- Requirement wording says "retry 3 times" but code may count total attempts differently
- Requirement doc may mention multiple `_admax` payload paths; code may parse only one
- Section 8 acceptance wording may imply runtime verification that existing unit tests do not fully replace
