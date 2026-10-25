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

Managing content with the dashboard
-----------------------------------

Double-click Manage Website.command in Finder, or choose Terminal > Run Task >
Manage website in VS Code. The manager opens at:

    http://127.0.0.1:4111/__manager/

Keep its terminal open while working. Press Control-C to stop. It uses Python 3.10+
and the same Ruby 3.4 setup as the preview launcher. Photo thumbnails use Pillow,
which is installed automatically in an isolated, ignored project folder on first
use; no CMS account is required. To launch it from a terminal:

    bash "Manage Website.command"

- Pages: choose New page, select its type, and fill in the title, description,
  writing, and tile details. Research, tutorials, student showcases, photography,
  creative work, and general pages are supported. Choose an existing page to
  edit it. The visual editor supports links, linked people, photo galleries,
  YouTube embeds, and PDFs; an HTML editor is also available.
- Headings: Heading on the page sets the main heading (H1). In the writing
  toolbar, choose Paragraph, Section heading (H2), Subsection heading (H3), or
  Subsubsection heading (H4) to format the selected text or current paragraph.
  The menu follows the heading level at the cursor. Use heading levels in order.
- Tooltips: hover over a field or button, or focus it with the keyboard, to see
  a short explanation. Press Escape to dismiss a tooltip. Help also works in
  dialogs, including the page, section, media, and S3 controls.
- Pictures & videos: use Add photos, Add video, and Manage media in the writing
  toolbar to edit that page's content. Click a picture in the visual
  editor to edit or remove it; the video edit dialog also has Remove video.
  Save & build preview applies your changes, and Review & publish sends them
  to the live website. Index tile pictures use the linked page's tile settings.
- Photos: upload several files together, or paste existing image URLs, one per
  line. Each photo has a full-size URL (opened on click), an optional small-image
  URL (displayed in the gallery), and a caption. You can paste these as:
  full-size URL | small-image URL | caption. A single URL, or URL | caption,
  also works. For pictures in the configured S3 website folder, a missing
  small-image URL is prepared automatically before insertion. Other image URLs
  use the same file for both views when no small-image URL is supplied.
  Existing small/full-size pairs are preserved. Uploaded media is added to
  assets/uploads when its page is saved. Existing S3 URLs continue to work.
  Choose photos from S3 browses the corresponding website folder. Existing
  small/full-size pairs are filled in together when both objects are known.
  If only the original exists, the manager downloads it, creates a thumbnail,
  uploads that thumbnail to S3, and fills in both URLs. Replacement pictures and
  new or changed page tile images use the same preparation. Existing page tiles
  are left alone when saving unrelated text edits.
- Manage media: inside the page editor, choose Manage media to see its existing
  pictures and videos. Replace / edit lets you upload a replacement photo or
  change its URL, caption, and image description. You may also apply that photo
  to the tile and sharing image. For videos, replace the YouTube URL or update
  its title, description, publication timestamp, and starting time. Remove
  deletes the selected item from the page content. Choose Done, then Save &
  build preview to save your changes. Existing media files are retained so
  other pages that use them are unaffected.
- Videos: paste a YouTube URL and choose Get video details. The manager attempts
  to retrieve the actual publication timestamp. If it cannot, supply the real
  upload datetime with its timezone before inserting the video.
- Arrange tiles: choose a section, move tiles earlier or later, and save.
  Existing custom image crops, overlays, and awards are retained.
- Sections: choose My Works, My Photography, My Creativity, or About Me, then
  add a section, edit its title, show or hide its heading, or move it with the
  arrows. Each move saves immediately and updates the preview. New sections
  appear first. Enable Show section links above the tiles to add jump links.
  The Page tile placement menu includes every current section and its main page.
  New page tiles default to position 1 within the section you choose.
  Removing a populated section asks whether to move its tiles into another
  section or remove those tiles from main pages. Linked pages and their files
  are kept. Moved tiles appear first in the destination, retaining their order
  and custom artwork. Undo section changes from Recent changes.
  These operations manage tile groups; headings inside page writing are set
  with the writing toolbar. Save locally, review the preview, then publish as usual.
- People & profile links: add or update collaborators' names, profile URLs, and
  aliases. Use Add person in the page editor to insert a shared linked name.
- Shared settings: change the default photo/favicon, email, CV URLs, and social
  profiles. These settings apply throughout the website.
- S3 files: browse bucket folders and filter by pictures, PDFs, videos, audio,
  archives, or all files. Choose from S3 buttons also appear beside page images,
  tile images, replacement-photo URLs, profile photos, and CV links. The PDF
  dialog can select an existing S3 PDF. Public access is checked before a link
  is inserted. The image picker starts in WorkImages, BlogImages, or
  CreativityImages according to the page section; PDF selection starts in Resume.
- Delete pages: select one or several detail pages in Pages. You may choose a
  replacement page for each deleted address. Main index pages are protected.
  If another page still links to a deleted page, a replacement or a link edit is
  required. With no replacement, a removed address correctly returns not found.
- Recent changes: undo the most recent saved operation. Local backups are kept
  in .site-manager/history, and undo refuses to overwrite later manual edits.

Save & build preview updates the page and tile together. The shared Jekyll
layout supplies the common header, footer, canonical URL, and sharing metadata;
the sitemap updates automatically. Renaming a page creates a redirect from its
previous address and updates existing links and older redirect targets.
Open website preview to review the resulting pages. Saving stays local.

To publish, open Review & publish and choose Review & validate. The manager runs
a production build and the site checks, then lists every changed file, including
manual changes outside the manager. Review this list, enter an update message,
and choose Publish changes to the website. This commits the listed changes and
pushes to main on origin; the existing GitHub Pages workflow then deploys them.
GitHub access and Git author details must already be configured on the computer.
If files change after review, a new review is required. If pushing fails after a
commit, the commit remains local and can be pushed with git push origin main.

The manager runs only on this computer. Its source, launchers, dependencies,
backups, pending uploads, and preview builds are excluded from the live site.
The unused Font Awesome package sources in assets/js-packages are also excluded
from builds; the site's actual styles, scripts, and webfonts remain included.
Undoing an already-published edit creates a local change; publish it again to
update the live website.

Main-page section titles, order, heading visibility, and jump-link settings live
in _data/sections.json. Tile content stays in _data/tiles.json. The shared layout
renders the configured sections below each main page's editable content. Section
IDs remain stable when renamed, and operations save both data files together
with conflict checks and undo backups. The production validator checks that
rendered sections, headings, and jump links match the configured order.

S3 connection and one-time cleanup
----------------------------------

In S3 files, enter the bucket, AWS region, website folder, and local AWS profile.
The defaults are worldofsoumyajit, us-east-1, My Website related Stuffs/, and
worldofsoumyajit. Choose Connect AWS and complete sign-in/MFA directly on AWS's
browser page. This uses aws login with temporary credentials; no console
password or access key is stored in the website files. Reconnect when the
temporary session expires. Connection settings are local to .site-manager.

If AWS CLI 2 is unavailable, choose Install AWS support or run:

    bash scripts/setup_aws.sh

The official AWS installer puts its verified CLI into .site-manager, without a
system-wide installation. AWS manages sign-in credentials in its standard local
cache outside the repository. Browsing S3 files only lists and selects files.
Choosing pictures for page content or tiles also creates any missing thumbnails;
removing media or deleting a page never deletes an S3 object automatically.

Automatic S3 photo thumbnails
-----------------------------

1. Upload original pictures to the website folder in S3, as usual.
2. In a page editor, choose Add pictures > Choose photos from S3 and select them.
   You can also paste original S3 URLs and choose Insert gallery.
3. The manager reuses existing small/full pairs or creates missing thumbnails.
   Gallery pictures and page tiles use the smaller URL, while clicking a gallery
   picture opens its original in the image viewer.
4. Save & build preview, review the page, and publish the page changes as usual.

New thumbnails are WebP images with a maximum width and height of 800 pixels.
They keep the original proportions, correct camera orientation, preserve
transparency, and do not upscale small pictures. EXIF/GPS information is removed
from thumbnails. Original files and their metadata remain untouched. Animated
images get a static first-frame preview; SVG files are reused without resizing.
Sources up to 50 MB and 50 million pixels are supported.

Generated images are stored in an _thumbnails subfolder beside the original
pictures. Their filenames include a version derived from the original S3 ETag,
so selecting a replaced original creates a fresh thumbnail URL. Uploads use
If-None-Match to prevent overwriting another file. Existing hand-made thumbnail
pairs and crops take precedence. Generated subfolders are hidden in the picker;
select the originals from their parent folder.

Thumbnail uploads happen immediately when pictures are prepared, before the page
is saved or published. Retrying after an interrupted operation reuses completed
uploads. Cancelling a page does not remove already-created thumbnails. The
manager must be running for this workflow; it does not install an AWS Lambda
function or process uploads while the manager is closed.

Your AWS profile needs s3:ListBucket for the website folder, s3:GetObject for
originals and thumbnails, and s3:PutObject for _thumbnails objects. The new images
must be publicly readable under your existing website access policy. For older
buckets where individual originals use public-read ACLs, the manager mirrors only
that grant to its own thumbnail; this additionally needs s3:GetObjectAcl on the
originals and s3:PutObjectAcl on thumbnails. It never changes bucket policies or
original-image permissions. If access is missing, the picker reports the error
and keeps the selection available to retry after reconnecting or fixing access.

To set up photo support manually, or repair an interrupted installation:

    bash scripts/setup_images.sh

The dependency environment lives in .site-manager/images-venv and stays out of
Git and the published website. To run all image and manager tests locally:

    .site-manager/images-venv/bin/python3 -m unittest discover -s scripts -p 'test_*.py'

The separate one-time cleanup tools are for an explicit audit and deletion:

    python3 scripts/audit_s3.py
    python3 scripts/cleanup_s3.py backup

The audit checks source HTML, shared configuration/data, styles/scripts, every
live sitemap page, and links in referenced PDFs. It accounts for full-size
photos, gallery images, metadata images, CVs, legacy plus-encoded URLs, and
literal plus signs. Folder markers and objects outside the website folder are
retained. Review .site-manager/s3-audit/deletion-candidates.csv before deletion.

Only after the audit, backup verification, and explicit approval of that list:

    python3 scripts/cleanup_s3.py delete-all --manifest .site-manager/s3-audit/backup/manifest.json

Alternatively, delete-images keeps unlinked PDFs. The tool checks the current
website again, skips objects that became referenced or changed, verifies every
local backup checksum, and uses an ETag condition on each S3 deletion. Backups,
object metadata/ACLs, and the deletion journal remain in .site-manager/s3-audit.
They are excluded from Git and the published site. A backed-up object can be
restored without overwriting a newer S3 object:

    python3 scripts/cleanup_s3.py restore --manifest .site-manager/s3-audit/backup/manifest.json --key "exact S3 object key"

Common settings
- _config.yml: site name, profile photo (also the favicon and default sharing
  image), email, shared organization and software links, CV links, social URLs, analytics
  ID, and shared stylesheet cache versions.
- _data/people.json: preferred profile URLs and name aliases for collaborators,
  advisors, and mentors. Update a person's URL here once to update every mention.
- _data/redirects.json: retired .html addresses mapped directly to their current
  pages. _plugins/legacy_redirects.rb generates these pages with the shared
  redirect layout, an immediate meta refresh, a canonical, and a fallback link.
- _data/tiles.json: ordered tiles for the homepage, photography, and creative
  indexes. _includes/tiles.html renders them. The dashboard maintains this file.
- _data/navigation.yml: menu labels and destinations; detail-page back links use
  the same entries.
- _data/social.yml: footer social-link labels and icons.
- _layouts/default.html: shared document structure.
- _layouts/detail.html: default layout plus a back link for research, tutorial,
  showcase, photo, and creative detail pages.
- _includes/: shared head, analytics, header, menu, footer, scripts, and back link.

The shared favicon uses profile_image with a favicon_version query parameter.
If the photo is replaced at the same URL or a browser keeps an old tab icon,
increase favicon_version in _config.yml, restart the local preview, and publish
the updated build to refresh the icon URL on every page.

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

To test the manager's create, edit, rename, delete, undo, media, and publishing
operations in temporary copies (including a temporary local Git remote):

    python3 -m unittest discover -s scripts -p 'test_*.py'

The GitHub Pages workflow builds and validates the site before uploading it
for deployment.

Adding a page
Use New page in the dashboard for routine additions. It handles the page, tile,
and related metadata together. To create a source file manually instead:

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
