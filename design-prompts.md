# Design Prompts — v0 (Vercel) & Lovable

Prompts derived from the KNA Enterprise Digital Archive SDD (Phase One).
Paste one section at a time — both tools produce better results with focused,
page-scoped prompts than one giant prompt. Generate the design system first,
then pages.

---

## 0. Master context block (prepend to EVERY prompt)

> You are designing the **Kenya News Agency Digital Archive**, a public
> eCommerce platform where citizens, journalists, researchers and businesses
> browse, license and purchase historical Kenyan photographs, newspapers,
> videos and audio from a national archive spanning several decades.
>
> **Tech constraints:** Next.js (App Router) + TypeScript + Tailwind CSS +
> shadcn/ui components only. Fully responsive, mobile-first. Accessible
> (WCAG AA, semantic HTML, keyboard navigable). No backend logic — use typed
> mock data and clearly-marked fetch placeholders that will call a REST API
> at `/api/v1`.
>
> **Brand feel:** dignified, archival, trustworthy — a national institution.
> Editorial layout inspired by museum/press archives: generous whitespace,
> strong typography (a serif for display headings, clean sans for UI), a
> restrained palette anchored on deep ink black, warm paper white, and one
> accent drawn from the Kenyan flag (deep red or green) used sparingly.
> Historical black-and-white photography is the hero of every page — the UI
> should recede behind the imagery. Include subtle watermark treatment on all
> image previews ("KNA — PREVIEW").

---

## 1. Design system / component kit

> Using the context above, create the foundational design system: color
> tokens (light mode primary, dark mode optional), typography scale, spacing,
> and these reusable components: AssetCard (image, title, year, category
> badge, price-from, hover zoom), CategoryPill, CollectionCard (cover image
> with overlay title and asset count), PriceTierTable (Thumbnail KES 50 /
> Preview KES 100 / High Resolution KES 500 / Editorial License KES 1,000 /
> Commercial License KES 2,000), LicenseBadge (Editorial, Commercial,
> Educational, Government, Internal Use), SearchBar with filter chips,
> Pagination, EmptyState, Toast, and OrderStatusBadge (Pending, Paid,
> Cancelled, Refunded, Completed).

## 2. Home page

> Design the landing page: full-bleed hero with a rotating historical
> photograph, headline "Kenya's history, preserved and licensed", prominent
> search bar, featured collections rail (Presidential Archives, Independence
> Collection, National Celebrations, Kenya Wildlife, Historical Newspapers),
> latest additions grid (AssetCard), category browse strip (Politics,
> Education, Sports, Health, Agriculture, Tourism, Infrastructure, National
> Events), a "how licensing works" 3-step section (Search → License → 
> Download), and a footer with institutional links.

## 3. Search results / browse page

> Design the search & browse experience: left sidebar filters (keyword,
> category, collection, asset type [Photograph, Video, Audio, PDF,
> Newspaper, Document], date range, photographer, county, tags), results
> grid of AssetCards with count, sort dropdown (Relevance, Newest, Oldest,
> Price low→high, Price high→low), active filter chips with clear-all,
> pagination at 20 per page, and a loading skeleton state plus an
> EmptyState for zero results.

## 4. Product detail page

> Design the asset detail page: large watermarked preview with zoom,
> metadata panel (title, caption, description, photographer & credit,
> publication date, location/county, historical period, tags as chips),
> license selector (radio cards explaining each license's usage rights),
> resolution/price tier selector using PriceTierTable, prominent
> "Add to Cart" CTA, related assets rail, and breadcrumbs
> (Home / Category / Asset).

## 5. Cart & checkout

> Design a two-page flow. Cart: line items (thumbnail, title, chosen license
> + resolution, unit price, remove), order summary card with subtotal and
> total in KES, "Proceed to Checkout". Checkout: single-page with order
> review, payment method selection as logo cards (eCitizen, M-Pesa, Visa,
> Mastercard), billing details form, terms checkbox, "Pay Now" CTA, and a
> success state showing order number with a "Go to Downloads" button.

## 6. Auth pages

> Design Login, Register (first name, last name, email, phone [+254],
> password + confirm with strength meter), Forgot Password, Reset Password,
> and Verify Email screens. Split-screen layout: form on the left, a
> full-height historical photograph with caption/credit on the right.
> Include inline validation states and API error alert styling.

## 7. Customer dashboard

> Design the account area with sidebar navigation (Overview, My Downloads,
> Order History, Profile, Security). Downloads: table/cards of purchased
> assets with license badge, remaining download count, expiry date, and a
> Download button. Orders: list with OrderStatusBadge and detail drawer.
> Profile: editable form. Security: change password.

## 8. Admin portal

> Design an admin layout (collapsible sidebar: Dashboard, Assets,
> Categories, Collections, Users, Orders, Reports, Settings) with a
> top bar showing role badge (Content Editor / Administrator / Super
> Administrator). Dashboard: stat cards (revenue, orders, downloads, new
> users) + recent orders table + top-selling assets. Assets: data table
> with status (Draft / Review / Published / Archived), bulk actions, and a
> multi-step upload dialog (file dropzone → metadata form → pricing &
> licenses → publish). Users: table with role and account status
> (Active/Suspended) and an invite-staff dialog. Orders: table with
> filters and a refund action behind a confirm dialog.

---

## Tips

- **v0**: generates shadcn/ui React directly — ask for "a single page as a
  set of composable components, no page-level data fetching" so output drops
  into `src/features/*`.
- **Lovable**: better for full multi-page flows — give it sections 0 + 2–7 in
  one project, then export and cherry-pick components.
- After generating, replace mock data with TanStack Query hooks calling the
  Django API and wire forms with React Hook Form + Zod (mirroring the DRF
  serializer rules: password ≥10 chars, phone `+?[0-9]{7,15}`).
