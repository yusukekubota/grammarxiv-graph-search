#!/usr/bin/env ruby
# frozen_string_literal: true

require "csv"
require "json"
require "ostruct"
require "open-uri"
require "fileutils"

# --- small helpers (only what the last 4 lines need) --------------------------

class Object
  def to_ostruct
    OpenStruct.new(self)
  end
end

class Array
  # Convert an array of OpenStruct-like objects to a TSV string.
  # `properties` is an array of column names (strings).
  def os_array2tsv(properties)
    rows = map do |obj|
      properties.map do |prop|
        obj.respond_to?(prop) ? obj.public_send(prop) : nil
      end
    end

    ([properties] + rows).map { |row|
      row.map { |v| v.to_s.tr("\t", " ").gsub("\n", "\\n") }.join("\t")
    }.join("\n")
  end
end

class String
  # Write string content to a file (creates parent directories).
  def writeToOutFile(filename)
    FileUtils.mkdir_p(File.dirname(filename))
    File.write(filename, self)
  end

  # Parse a TSV string into an array of OpenStruct.
  def read_tsv2os
    data = gsub(/\r/, "")
    CSV.new(data, headers: true, col_sep: "\t", liberal_parsing: true)
       .map(&:to_h)
       .map(&:to_ostruct)
  end

  # Download a Google Sheets "export?format=tsv" URL and parse it into OpenStructs.
  def read_GSheet2os
    tsv = URI.open(self, &:read)
    tsv.read_tsv2os
  end
end

# --- data loading ------------------------------------------------------------

def make_url(gid)
  # Spreadsheet id is hard-coded in the original script.
  "https://docs.google.com/spreadsheets/d/12kSfJdC9o99cNvis-f4g5m6uclF_37NLoYEh58J3g3c/export?format=tsv&gid=#{gid}"
end

HypNameSheetURL       = make_url("1826693149")
FrameworkNameSheetURL = make_url("1723178886")
TopicNameSheetURL     = make_url("2023287325")
PubNameSheetURL       = make_url("1194994121")
AuthorNameSheetURL    = make_url("296545536")
RelSheetURL           = make_url("1972451989")

Hyp_entries = HypNameSheetURL.read_GSheet2os.map { |x| x.type = "hypothesis"; x }

Framework_entries = FrameworkNameSheetURL.read_GSheet2os.map { |x| x.type = "framework"; x }

Topic_entries = TopicNameSheetURL.read_GSheet2os.map do |x|
  x.type = "topic"
  x.sub_type = x.subType.to_s.downcase
  x
end

Pub_entries = PubNameSheetURL.read_GSheet2os.map do |x|
  x.type = "publication"
  x.sub_type = x.subType.to_s.downcase
  x
end

Author_entries = AuthorNameSheetURL.read_GSheet2os.map do |x|
  x.type = "author"

  # semanticScholarAuthorIds is expected to be a JSON array string.
  ids = begin
    JSON.parse(x.semanticScholarAuthorIds.to_s)
  rescue JSON::ParserError
    []
  end
  first_id = ids.is_a?(Array) ? ids.first : ids
  x.name = "#{x.name}, #{first_id}" if first_id && first_id.to_s != ""

  x
end

All_entries = Hyp_entries + Framework_entries + Topic_entries + Pub_entries + Author_entries

id_name_hash = All_entries.map { |x| [x.id, x.name] }.to_h

Rel_entries = RelSheetURL.read_GSheet2os.map do |x|
  x.from = id_name_hash[x.fromEntryId]
  x.to   = id_name_hash[x.toEntryId]
  x.type = "relation"
  x.subType = x.subType.to_s.downcase
  x
end


All_entries.map(&:name).uniq.join("\n").writeToOutFile("./result/entry_names.txt")
All_entries.os_array2tsv(%w[name type sub_type entry summary]).writeToOutFile("./result/entries.tsv")
Rel_entries.os_array2tsv(%w[id name type subType variant fromEntryId toEntryId from to]).writeToOutFile("./result/rels.tsv")
Rel_entries.os_array2tsv(%w[from from_type type to to_type]).writeToOutFile("./result/rels_w_type.tsv")
