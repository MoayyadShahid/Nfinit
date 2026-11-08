# Studio components

Adapted from [Kokonut UI](https://kokonutui.com/) under the included MIT license:

- [AI State Loading](https://kokonutui.com/docs/ai/ai-loading): explicit run events, server-reported step durations, bounded scrolling and collapsible details. No simulated work or percentage. Completion remains the saved revision/chat response.
- [Command Palette](https://kokonutui.com/docs/navigation/action-search-bar): Studio commands, project and revision search. Radix Dialog and cmdk supply modal focus and keyboard navigation. Actions call the existing handlers, including their payment and unsaved-change checks.
- [AI Model Selector](https://kokonutui.com/docs/ai/ai-model-selector): controlled model selection from `MODEL_CONFIGS`, shared by the composer and editor. No demo models or unsupported effort settings.
- [Smooth Drawer](https://kokonutui.com/docs/navigation/smooth-drawer): mobile export sheet using Vaul, with drag dismissal, a Cancel button and safe-area padding. Checkout example removed; all formats use the existing export handler.

Source reviewed and adapted on 2026-11-07. Colors use Nfinit's semantic tokens. Animation respects reduced motion. These components do not fetch external data, execute HTML, store prompts, or add analytics. Re-importing upstream files would replace these adaptations and requires another review.
