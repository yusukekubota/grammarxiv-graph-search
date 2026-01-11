#!/usr/bin/env ruby
# coding: utf-8

require "ostruct"
require "csv"
require "cgi"
require 'open3'
require 'google_drive'
require 'stringio'
require 'digest/md5'

#require 'dotenv'

if ENV['GTOOLS_WEB']
then
  Username = ENV['GX_USER']
  SpreadSheetKey = ENV['SPREADSHEET_KEY']
  Session = GoogleDrive::Session.from_config("../config.json")
else
  Username = "yuusukekubota@gmail.com"
  SpreadSheetKey = "17yB-GCWVN9tLl4nHJkTIYn-XyUcrdIPQIKjp5aVIFio"
  Session = GoogleDrive::Session.from_config("../config.json")
end


def delete_record(ws, row)
  (1..ws.num_cols).map { |col| ws[row, col] = "" }
end

def delete_all_records(ws)
  (1..ws.num_rows).map { |row| delete_record(ws,row) }
end

def makeURL(gid)
  "https://docs.google.com/spreadsheets/d/#{SpreadSheetKey}/export?format=tsv&gid=#{gid}"
end

def makeURL2(gid)
  "https://docs.google.com/spreadsheets/d/12kSfJdC9o99cNvis-f4g5m6uclF_37NLoYEh58J3g3c/export?format=tsv&gid=#{gid}"
end


HypNameSheetURL = makeURL2("1826693149")
FrameworkNameSheetURL = makeURL2("1723178886")
TopicNameSheetURL = makeURL2("2023287325")
PubNameSheetURL = makeURL2("1194994121")
AuthorNameSheetURL = makeURL2("296545536")

RelSheetURL = makeURL2("1972451989")


TopicTypes = %w(keyword
language
vocabulary
research_question)

DataTypes = %w(acceptability
generalization
report)

BibTypes = %w(journal-article
article
proceedings-article
incollection
book
phdthesis
unpublished
inproceedings
misc
mathesis
ms
bathesis)

HypTypes = ["hypothesis"]

FrameworkTypes = ["framework"]

Rel_with_type = { "related_topic" => "related_topic [X->T]",
                  "true" => "true [P->DEFHPR]",
                  "false" => "false [P->DEFHPR]",
                  "uncertain" => "uncertain [P->DEFHPR]",
                  "trued_by" => "true [P->DEFHPR]",
                  "falsed_by" => "false [P->DEFHPR]", 
                  "entail" => "entail [DEFH->DEFH]",
                  "refer_to" => "refer_to [P->DEFHPR]",
                  "can_explain" => "can_explain [DEFHPR->DEFHPRT]",
                  "other_asymmetric" => "other_asymmetric [X->X]",
                  "other_symmetric" => "other_symmetric [X->X]",
                  "incompatible" => "incompatible [DEFHP->DEFHP]",
                  "subtopic_of" => "subtopic_of [T->T]",
                  "author_of" => "author_of [A->P]",
                  "equivalent" => "equivalent [X->X]",
                  "less_acceptable_than" => "less_acceptable_than [D->D(acceptability)]"
                }

def anonymous?
  Username == "anonymous"
end

def find_duplicate(ary)
  ary.select{ |e| ary.count(e) > 1 }.uniq
end

def read_GSheet(url)
  Open3.capture3("curl -L #{url.quote}").first
end

def write_to_gsheet(sheet_name, data)
  ws = Session.spreadsheet_by_key(SpreadSheetKey).worksheet_by_title(sheet_name)
  last_row = (1..ws.num_rows).map { |row| row unless ((ws[row,1] == "") and (ws[row,2] == "")) }.compact.max
  ws.update_cells(last_row+1, 1, data)
  new_last_row = (1..ws.num_rows).map { |row| row unless ((ws[row,1] == "") and (ws[row,2] == "")) }.compact.max
  ws.save
  puts "#{sheet_name}を更新しました。"
end

def write_to_gsheet_alt(sheet_name, data, left, top)
  ws = Session.spreadsheet_by_key(SpreadSheetKey).worksheet_by_title(sheet_name)
  ws.update_cells(left, top, data)
  ws.save
  puts "#{sheet_name}を更新しました。"
end

def super_type(type)
  if TopicTypes.member?(type) then "topic"
  elsif BibTypes.member?(type) then "publication"
  elsif HypTypes.member?(type) then "hypothesis"
  elsif FrameworkTypes.member?(type) then "framework"
  else "data"
  end
end


class Object
  def quote
    '\'' + self.to_s + '\''
  end

  def to_ostruct
    OpenStruct.new(self)
  end

  def to_rel_entry
    RelEntry.new(self)
  end

  def clean_text
    self&.gsub(/(?!\n)[[:cntrl:]]/,"")
  end

end

class Array

  def os_array2tsv(properties)
    self.map { |x| x.get_properties(properties)}.write_to_tsv(properties)
  end
  
  def print_list
    self.map(&:join_t).join("\n")
  end
  
  def join_t
    self.join("\t")
  end

  def delete_void_entries
    self.select { |x| x.id || x.name }
  end

  def write_to_tsv(header)
    a = [header] + self
    a.print_list
  end

  def get_recent_summary
    self
      .select { |x| anonymous? or x.added_by == Username }
      .last(5).map { |x| x.name&.get_summary }
  end
  
end

class String

  def writeToOutFile (filename)
    out_file = File.open(filename, 'w')
    out_file.puts(self) 
    out_file.close
  end
  
  def read_tsv2os
    data = self.gsub(/\r/,'')
    CSV.new(data, headers: true, col_sep: "\t", liberal_parsing: true).map(&:to_ostruct)
  end

  def get_summary
    (Summary_entries | Rel_entries).select { |x| x.name == self }.first
  end

  def read_GSheet2os
    read_GSheet(self)
      .read_tsv2os
      .delete_void_entries
      .map { |x| x.type ||= "relation" if x.relation; x }
  end
  
  def read_GSheet2os_alt
    read_GSheet(self)
      .read_tsv2os
      .map { |x| x.type ||= x.data_type; x }
      .map { |x| x.type ||= "relation" if x.relation; x }
  end
  
end

class OpenStruct

  def add_cuid
        self.id = CUIDGenerator.generate_cuid
        self
  end
  
  def record2AppSheetData
    [id, name, type, sub_type, example_string, example_annotated, acceptability, gloss, translation, paraphrase, context, antecedent_expression, antecedent_entry, description, object_language, description_language, other_info, example_formatted, added_by]
  end
  
  def record2AppSheetHyp
    [id, name, type, sub_type, specific_to, description, description_language, other_info, added_by]
  end
  
  def record2AppSheetFramework
    [id, name, type, sub_type, specific_to, description, description_language, other_info, added_by]
  end
  
  def record2AppSheetBib
    [id, name, "publication", sub_type, author, year, title, published_in, editor, volume, issue, pages, publisher, abstract, published, publication_language, publication_id, added_by]
  end
  
  def record2AppSheetRel
    [id, name, from, relation_w_type, relation_w_type, to, other_info, "", "", "", added_by, from_type, to_type]
  end
  
  def data_entry?
    self.type == "data"
  end
  
  def hyp_entry?
    self.type == "hypothesis"
  end
  
  def framework_entry?
    self.type == "framework"
  end
  
  def topic_entry?
    self.type == "topic"
  end
  
  def bib_entry?
    self.type == "publication"
  end
  
  def my_entry?
    self.added_by == Username
  end
  
  def get_properties(properties)
    properties.map { |x| self.send(x) }
  end

  def added_by0
    self.added_by&.gsub(/@.+/,"")
  end

  def summary_short
    "<small>#{self.summary[0,39]}...</small>"
  end

  def url_link
    "<a href='#{self.url}' target='_blank' rel='noopener noreferrer'>link</a>"
  end

  def neo4j
    neo4j_url = "https://bloom.neo4j.io/index.html?connectURL=neo4j%2Bs%3A//351463fc.databases.neo4j.io&search=#{CGI.escape(self.name.to_s)}&run=true"
    "<a href='#{neo4j_url}' target='_blank' rel='noopener noreferrer'>link</a>"
  end


  def add_missing_fields_rel
    if self.direction == "incoming"
    then
      self.from = self.target
      self.to = self.pivot
      self.from_type = target_type
      self.to_type = pivot_type 
    else
      self.from = self.pivot
      self.to = self.target
      self.from_type = pivot_type 
      self.to_type = target_type
    end
    self.name = "#{self.from}-#{self.relation}-#{self.to}"
    #self.id = self.name
    self.id = CUIDGenerator.generate_cuid
    self.type = "relation"
    self.relation = self.relation.to_s
    self.relation_wo_type = self.relation
    self.relation_w_type  = Rel_with_type[self.relation]
    self.to_type ||= super_type(Summary_entries.select { |y| y.name == self.to }.first&.type)
    self.from_type ||= super_type(Summary_entries.select { |y| y.name == self.from }.first&.type)
    self.added_by = Username

    self
  end


  
  def add_missing_fields_non_rel
    self.name = self.target
    #self.id = Time.new.to_s.split.slice(0..1).join("_")
    self.id = CUIDGenerator.generate_cuid
    self.added_by = Username
    self.acceptability = self.acceptability&.gsub(/\\/,"")
    self.type = super_type(self.sub_type)
    self
  end
  
  def record2AppSheetSummary
    [id, name, type0, summary, description0, added_by, relations, url].map(&:clean_text)
  end

  def record2AppSheetComp
    [id0, name].map(&:clean_text)
  end

  
end

class RelEntry < OpenStruct
  def initialize(h = {})
    super(h)
    self[:name] ||= self[:id]
  end

  def to_s
    [from, type, to].join(" ")
  end
  
  def summary
    self.to_s
  end
  
  def has_argument?(arg)
    self.from == arg || self.to == arg
  end

  def mask_argument_name(str)
    self.to = "@_" if self.to == str
    self.from = "@_" if self.from == str
    self
  end

end

class NonRelEntry < OpenStruct
  def initialize(h = {})
    super(h)
  end
end

class DataEntry < NonRelEntry 
  def initialize(h = {})
    super(h)
    self[:type] = "data"
  end
end

class BibEntry  < NonRelEntry 
  def initialize(h = {})
    super(h)
    self[:type] = "publication"
  end
end

class HypEntry  < NonRelEntry 
  def initialize(h = {})
    super(h)
    self[:type] = "hypothesis"
  end
end

class FrameworkEntry < NonRelEntry 
  def initialize(h = {})
    super(h)
    self[:type] = "framework"
  end
end

class TopicEntry  < NonRelEntry 
  def initialize(h = {})
    super(h)
    self[:type] = "topic"
  end
end

class CUIDGenerator
  BASE36_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'.chars.freeze
  @@counter = 0
  @@last_timestamp = 0

  def self.generate_cuid
    timestamp = (Time.now.to_f * 1000).to_i

    if timestamp == @@last_timestamp
      @@counter += 1
    else
      @@last_timestamp = timestamp
      @@counter = 0
    end

    timestamp_base36 = encode_base36(timestamp)
    counter_base36 = encode_base36(@@counter)
    fingerprint = get_machine_fingerprint
    random_string = get_random_string(4)

    "c#{timestamp_base36}#{counter_base36}#{fingerprint}#{random_string}"
  end

  private

  def self.encode_base36(value)
    return '0' if value == 0

    result = ''
    while value > 0
      result = BASE36_CHARS[value % 36] + result
      value /= 36
    end
    result
  end

  def self.get_machine_fingerprint
    begin
      hostname = `hostname`.strip
      hash_value = Digest::MD5.hexdigest(hostname)
      hash_value[0..3]
    rescue
      '0000'
    end
  end

  def self.get_random_string(length)
    Array.new(length) { BASE36_CHARS.sample }.join
  end
end


Hyp_entries = HypNameSheetURL.read_GSheet2os.map { |x| x.type = "hypothesis"; x } 
Framework_entries = FrameworkNameSheetURL.read_GSheet2os.map { |x| x.type = "framework"; x } 
Topic_entries = TopicNameSheetURL.read_GSheet2os.map { |x| x.type = "topic"; x.sub_type = x.subType.to_s.downcase ; x }   
Pub_entries = PubNameSheetURL.read_GSheet2os.map { |x| x.type = "publication"; x.sub_type = x.subType.to_s.downcase ; x }
Author_entries = AuthorNameSheetURL.read_GSheet2os.map { |x| x.type = "author" ; x.name = x.name.to_s + ", " + JSON.parse(x.semanticScholarAuthorIds).first.to_s  ; x }
