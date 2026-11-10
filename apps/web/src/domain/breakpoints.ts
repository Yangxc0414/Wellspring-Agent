/** Layout breakpoint shared by JS media queries and the CSS media queries.
 * Previously 1150px was hard-coded in App.tsx, TopBar.tsx and several CSS files.
 */
export const NARROW_LAYOUT_PX = 1150;
export const NARROW_LAYOUT_QUERY = `(max-width: ${NARROW_LAYOUT_PX}px)`;
