#!/usr/bin/env ruby
# coding: utf-8
require_relative 'GToolsWebLib'
#require "ostruct"
require "optparse"
require 'json'

  
All_entries = Hyp_entries + Framework_entries + Topic_entries + Pub_entries + Author_entries

id_name_hash = All_entries.map { |x| [x.id, x.name] }.to_h

Rel_entries = RelSheetURL.read_GSheet2os.map(&:to_rel_entry)
                .map { |x| x.from = id_name_hash[x.fromEntryId] ; x.to = id_name_hash[x.toEntryId] ; x.type = "relation" ; x.subType = x.subType.downcase ; x }

#p AuthorNameSheetURL


All_entries.map(&:name).uniq.join("\n").writeToOutFile("../result/entry_names.txt")  

All_entries.os_array2tsv(%w(name type sub_type entry summary)).writeToOutFile("../result/entries.tsv")
Rel_entries.os_array2tsv(%w(id name type subType variant fromEntryId toEntryId from to)).writeToOutFile("../result/rels.tsv")
Rel_entries.os_array2tsv(%w(from from_type type to to_type)).writeToOutFile("../result/rels_w_type.tsv")

#All_entries.select { |x| x.entry == "author" }.map { |x| x.details + ", " + x.name }.join("\n").writeToOutFile("../result/author-list.txt")
