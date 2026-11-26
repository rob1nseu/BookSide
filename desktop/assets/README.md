# Companion sprite

`companion.png` is a transparent RGBA sheet, four equal-width cells: smiling idle,
blink, reading, sleeping. Qt slices the sheet at runtime; no generated file outside
the repository is required. The current sheet was generated with the built-in
imagegen tool on 2026-11-26, using the previous front-facing sheet as reference.

## Current revision: modestly round pet, small fixed size

Generated with built-in imagegen; stored in `desktop/assets/companion.png`. Runtime size is fixed at 130×170. Current final prompt:

> Refine this FRONT FACING Nailong desktop pet sprite strip. Keep reference proportions almost exactly: only about 5 percent fuller tummy, NOT obese, NOT broad pear shape, NOT squat or flattened. Same head, normal short legs, arms and height, modestly rounded body, Southeast University belly badge. Four equal horizontal cells, identical baseline, full body, clean truly transparent RGBA outside characters, generous transparent margins. Frame 1 warm smile open eyes holding green closed book beside body; frame 2 same pose smiling blink eyes closed; frame 3 facing front looking down reading open green book with both hands; frame 4 peacefully sleeping eyes closed gently hugging closed green book, slight head tilt. 3D soft yellow character. Do not reuse waving pose. No background, no floor, no frame, no letters outside badge, no sparkles. Maintain slender friendly original body, just very slightly rounder than this reference.

## Current app icon

The final icon is the editable `frontend/public/app-icon.svg`, shared by web brand, favicon and Qt/tray. It uses only Nailong yellow `#F2CF55` and Southeast University green `#536D59`, integer pixel coordinates and a transparent background. The raised book cover faces the user; only the head, eyes and small hands remain. No raster asset is required for this icon.

A built-in imagegen concept was explored with the prompt “two-color flat pixel Nailong head peeking over a raised green book, upper body only, no gradients”. The generated concept still had tonal variation, so it was not shipped. The final SVG is a native, hand-authored icon, rather than a recolored raster.

## Previous book icon (removed)

Historical imagegen prompt for the removed raster book icon:

> Create a single app icon for BookSide: an open book drawn in a refined colored-pencil / graphite sketch style, restrained academic artistic feeling. Front three-quarter top view, open cream paper pages with minimal faint graphite hatching, visible LEFT cover in desaturated Southeast University sage/forest green (#637966), visible RIGHT cover in desaturated warm golden yellow (#c7b568). Two covers clearly distinguishable along bottom and outer edges. Small simple silhouette immediately recognizable at 32px; crisp charcoal outlines, sparse pencil grain, not photorealistic, no words, no logo, no letters, no extra objects, no decorative sparkles. Book centered and occupies 85 percent of square canvas with generous clean transparent margins. Genuine transparent alpha background, no white tile, no rounded square background, no cast shadow. High quality transparent PNG suitable as application logo and favicon.

## Previous wider revision (superseded)

> Edit this desktop pet sprite sheet. Produce ONE transparent RGBA PNG horizontal strip of FOUR equally sized cells, width divisible by 4, no borders or backgrounds, genuine clean alpha=0 outside characters (NO ghost image / colored speckles). Character must stay FRONT FACING looking toward user, same soft yellow cute Nailong, Southeast University circular belly emblem and green book. Make body MUCH rounder and chubbier, broad pear-shaped squishy belly, squat short legs, head flowing smoothly into shoulders instead of distinct narrow neck, soft cuddly silhouette like original Nailong. Match exact scale and centered baseline across all four cells with generous transparent margins. New frame order left to right: 1) awake warm smile, open eyes, holding closed green book at side. 2) same pose but closed eyes and joyful smiling blink. 3) both hands holding OPEN green book, eyes looking down visibly reading, still facing front. 4) peaceful sleeping pose, closed relaxed eyelids, hugging closed green book at chest, very slight head tilt, gentle closed smile. All full body complete feet, 3D soft studio lighting, no floor, no shadow outside silhouette, no caption, no box, no grid. Preserve emblem yellow black green identity and lettering as well as possible. This is a production animation sprite sheet.
