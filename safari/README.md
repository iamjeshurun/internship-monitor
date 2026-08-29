# Safari review helper

Safari Web Extensions must be wrapped in a signed macOS app by Xcode. The reusable
extension source is in `../browser-extension`; it fills reviewed fields but never
clicks a submit button.

1. Install the full current Xcode from the Mac App Store and open it once.
2. Run `zsh safari/convert.sh` from the project root.
3. In Xcode, select your personal development team and run the generated macOS app.
4. In Safari, enable the extension under **Safari > Settings > Extensions**.

The converter is not included with Command Line Tools alone. No X developer API
account is needed for this local Safari helper; Xcode may ask for a free Apple ID
development team for local signing.
