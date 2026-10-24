# frozen_string_literal: true
require "json"
require "yaml"
require "date"

request = JSON.parse(STDIN.read)
if request.fetch("action") == "load"
  result = request.fetch("documents").map do |text|
    YAML.safe_load(text, permitted_classes: [Date, Time], aliases: false) || {}
  end
  puts JSON.generate(result)
else
  puts YAML.dump(request.fetch("data"), line_width: -1)
end
