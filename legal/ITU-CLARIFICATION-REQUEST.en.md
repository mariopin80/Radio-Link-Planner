# Draft email — clarification of ITU-R digital product permissions

**Status: DRAFT — NOT SENT.** 2026-11-18.

**Suggested recipient:** jur@itu.int (official ITU copyright contact listed at https://www.itu.int/home/Copyright/). The appropriate responsible ITU-R department may be different; ask for redirection if necessary.

**Subject:** Permission clarification: client-side ITU-R P.1812-8/P.2001-6 digital maps in commercial planning software

Dear ITU Copyright / ITU-R team,

I am the developer of Radio Link Planner, a Windows desktop application for terrestrial radio-link and coverage planning. I am preparing free, non-professional and paid professional editions, and would like to confirm the permitted use of the integral digital products associated with Recommendations **ITU-R P.1812-8 (09/2025)** and **ITU-R P.2001-6 (09/2025)**.

The application implements these methods using independently licensed Python implementations (Py1812 and Py2001) and needs the official digital tables/maps associated with the Recommendations. **We do not package, copy, mirror or redistribute the ITU data files** in our repository, executable, installer, or a server operated by us. Instead, on initial use, the client application downloads the official component ZIP files directly from the ITU website, processes the required data locally, and caches the derived local arrays in that individual user's private application-data directory. Calculations then operate locally without transmitting these ITU data to our servers.

Before commercial release, could you please clarify in writing:

1. May an individual purchaser of commercial desktop software download, locally convert and cache the integral digital products accompanying P.1812-8 and P.2001-6 for running propagation calculations in that application?
2. May our software automate the **direct client-to-ITU download** of these public component ZIPs without a separate redistribution licence, provided the resulting files remain on the user's computer?
3. Does the presence of paid professional licences alter that permission, even though the software vendor does not receive, host or distribute the data?
4. Is a separate licence, registration, required acknowledgement, direct-user acceptance, or other written permission required? If so, what is the correct procedure and contact?
5. Are there additional restrictions on distribution of **calculated propagation results and technical reports**, as distinct from the underlying ITU digital data files?

We can add an explicit user acknowledgement and technical safeguards if needed. We would appreciate a written response or a pointer to the specific licence terms that apply to this use case.

Thank you for your guidance.

Mario Pin — PU2PTU
Radio Link Planner
https://github.com/mariopin80/Radio-Link-Planner

---

Internal references for the request:

- https://www.itu.int/en/about/Pages/terms-of-use.aspx
- https://www.itu.int/en/ITU-R/study-groups/rsg3/rwp3m/Pages/digprod.aspx
- https://www.itu.int/rec/R-REC-P.1812-8-202509-I/en
- https://www.itu.int/rec/R-REC-P.2001-6-202509-I/en
- `src/radiolink/itu_data.py`: direct ITU component downloads and per-user cache.
- `.github/workflows/windows-mvp.yml`: tests rejecting redistribution of the integral digital datasets.
