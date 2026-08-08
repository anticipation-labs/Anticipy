/**
 * The trademark mark as an inline-styled HTML string, for email.
 *
 * Deliberately lives in lib/ rather than alongside the React component: the
 * email templates are rendered server-side with no React in the picture, and
 * importing a .tsx component file into that path drags JSX into a module that
 * has no business compiling it.
 *
 * Email clients strip <style> blocks, so the mark carries its own inline CSS.
 * Outlook's Word renderer ignores `vertical-align: super`, but it does honour
 * the presentational <sup> tag itself — so the element does the work there,
 * and the CSS refines it in every other client.
 *
 * Kept visually identical to the <Tm /> component in
 * src/components/Tm.tsx. If one changes, change both.
 */
export const TM_HTML =
  '<sup style="font-size:0.42em;line-height:0;vertical-align:super;font-weight:400;letter-spacing:0;opacity:0.55;margin-left:0.06em;">&#8482;</sup>';
