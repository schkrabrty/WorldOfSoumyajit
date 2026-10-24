# frozen_string_literal: true

module WorldOfSoumyajit
  # Keep retired filenames working without maintaining a duplicate HTML page each.
  class LegacyRedirects < Jekyll::Generator
    safe false
    priority :low

    def generate(site)
      redirects = site.data.fetch("redirects", {})
      pages_by_url = site.pages.to_h { |page| [page.url, page] }
      occupied = (pages_by_url.keys + site.static_files.map(&:relative_path)).map(&:downcase)

      redirects.each do |old_url, target_url|
        unless old_url.match?(%r{\A/[A-Za-z0-9_-]+\.html\z}) && !occupied.include?(old_url.downcase)
          raise Jekyll::Errors::FatalException, "Invalid or conflicting legacy URL: #{old_url}"
        end

        target = pages_by_url[target_url]
        unless target && target.data["sitemap"] != false && !target.data["redirect_to"]
          raise Jekyll::Errors::FatalException, "Legacy URL #{old_url} needs a public, direct target: #{target_url}"
        end

        page = Jekyll::PageWithoutAFile.new(site, site.source, "", old_url.delete_prefix("/"))
        page.data.merge!(
          "layout" => "redirect",
          "title" => target.data["title"],
          "permalink" => old_url,
          "canonical" => target_url,
          "redirect_to" => target_url,
          "redirect_title" => target.data["title"],
          "sitemap" => false,
          "assets" => false,
          "analytics" => false
        )
        page.content = '<p>This page has moved. <a href="{{ page.redirect_to | relative_url }}">Continue to {{ page.redirect_title | escape }}</a>.</p>'
        site.pages << page
        occupied << old_url.downcase
      end
    end
  end
end
