Phantom by HTML5 UP
html5up.net | @ajlkn
Free for personal and commercial use under the CCA 3.0 license (html5up.net/license)


This is Phantom, a simple design built around a grid of large, colorful, semi-interactive
image tiles (of which you can have as many or as few as you like). Makes use of some
SVG and animation techniques I've been experimenting with on that other project of mine
you may have heard about (https://carrd.co), and includes a handy generic page for whatever.

Demo images* courtesy of Unsplash, a radtastic collection of CC0 (public domain) images
you can use for pretty much whatever.

(* = not included)

AJ
aj@lkn.io | @ajlkn


Credits:

	Demo Images:
		Unsplash (unsplash.com)

	Icons:
		Font Awesome (fontawesome.io)

	Other:
		jQuery (jquery.com)
		Responsive Tools (github.com/ajlkn/responsive-tools)


My website address: https://worldofsoumyajit.com

Maintaining this site
---------------------

The site is built with Jekyll. Root .html files contain page metadata between
--- lines followed by each page's own HTML content. Shared layouts and includes
supply the surrounding document, header, menu, footer, styles, and scripts.
Existing .html addresses are retained through each page's permalink setting.

Common settings
- _config.yml: site name, profile photo (also the favicon and default sharing
  image), email, shared organization and software links, CV links, social URLs, analytics
  ID, and shared stylesheet cache versions.
- _data/people.json: preferred profile URLs and name aliases for collaborators,
  advisors, and mentors. Update a person's URL here once to update every mention.
- _data/redirects.json: retired .html addresses mapped directly to their current
  pages. _plugins/legacy_redirects.rb generates these pages with the shared
  redirect layout, an immediate meta refresh, a canonical, and a fallback link.
- _data/navigation.yml: menu labels and destinations; detail-page back links use
  the same entries.
- _data/social.yml: footer social-link labels and icons.
- _layouts/default.html: shared document structure.
- _layouts/detail.html: default layout plus a back link for research, tutorial,
  showcase, photo, and creative detail pages.
- _includes/: shared head, analytics, header, menu, footer, scripts, and back link.

Use the shared person include for names in page content:

    {% include person.html id="sarah_creem_regehr" name="Sarah H. Creem-Regehr" %}

The name argument preserves the form used in an author list or description.
Add new_tab=true to open the profile in a new tab. Add a person's full name and
any short names used in the page text to their aliases list. Validation checks
that every visible alias links to the preferred profile, including author lists.

Testing the website locally
---------------------------

For each editing session:

1. Double-click Preview Website.command in Finder on macOS. It builds the
   website and opens http://127.0.0.1:4000/ in your browser.
2. Keep the terminal open while editing HTML, CSS, or shared templates. Saving
   changes automatically rebuilds the site and refreshes the browser.
3. Test links, menus, images, and different browser widths to check the desktop
   and mobile layouts.
4. When finished, press Control-C in the terminal to stop the preview.

In VS Code, choose Terminal > Run Task > Preview website for the same preview.
If you change _config.yml, stop and restart the preview.

The launcher finds Ruby 3.4 and installs the locked dependencies into ignored
project folders when needed.

Opening a source .html file directly or using Live Server on the repository
root skips Jekyll, so it shows unstyled source content without the shared header,
menu, or footer. Use the preview launcher above for editing. To inspect a built
page with a static server, serve _site after a Jekyll build instead of the root.

To run the preview from a terminal:

    bash scripts/preview_site.sh

Build and validation checks
---------------------------

To build or serve manually, use Ruby 3.4 and Bundler:

    bundle install
    bundle exec jekyll serve

To build and validate the generated output:

    bundle exec jekyll build --trace
    python3 scripts/validate_site.py _site

The GitHub Pages workflow builds and validates the site before uploading it
for deployment.

Adding a page
Create a root .html file with metadata such as:

    ---
    title: "My new page"
    permalink: "/my-new-page.html"
    description: "A short description of this page."
    ---
    <h1>My new page</h1>
    <p>Page content goes here.</p>

The default layout is automatic. For a page with a back link, also set
layout: detail and section: works, photography, or creativity. A custom image
setting overrides the shared social-preview image. Existing JSON-LD metadata
is stored in each relevant page's structured_data setting.
For VideoObject metadata, uploadDate must be the video's actual publication
datetime, including its timezone (for example, 2024-08-30T07:30:40-07:00), rather
than the project year or recording date. Existing values were verified against
the embedded videos' public YouTube uploadDate metadata. Validation rejects
invalid dates and timestamps without a timezone.

The sitemap is generated from public HTML pages on every build; no manual URL
list needs updating. Link new content from its appropriate index or another
public page so visitors and crawlers can discover it. Set sitemap: false and
robots: "noindex, follow" for a page that should stay out of search results.
The error and elements pages use those settings. Historical redirects stay out
of the sitemap and point to their replacement's canonical URL. These are static
HTML redirects, not HTTP 301 responses; Google supports immediate meta refresh
redirects as a permanent redirect signal. Keep old URL mappings after renaming
a page, and point them straight to the current page to avoid redirect chains.
Shared templates, configuration, plugins, and development scripts are excluded
from the published output. The Google
verification file is published unchanged, and robots.txt declares the sitemap.
