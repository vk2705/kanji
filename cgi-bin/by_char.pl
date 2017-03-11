#!/usr/local/bin/perl -w -CS
use lib '/var/www/cgi-bin';

use strict;
use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);
require Encode;
use Encode qw/encode decode/;
use KanjiLookup;
use HTML::Entities;

my $q = CGI->new();

print $q->header( -charset=> "utf-8" ) ;

print "<html lang=\"ja\">\n";

my(%form);

foreach my $p (param()) {
    my $v = param($p);
    $v =  decode_entities($v);
    $form{$p} = $v;    
}

###########

setup_tables();

my $n = $form{char};

die "undef param char!\n" if (!defined $n) ;

print "SEARCH PARAMETER: $n </BR>\n";

my $e = get_by_char($n);

if (!defined $e) {
    print " not found \n";    
    print end_html;
    exit (0);
}


#print  join( ';', @lst) . "<BR>\n";
print "<TABLE BORDER=1> <TH>Alternative names</TH> <TH>Id</TH> <TH>Kanji</TH>  \n";
print "<TR>";

my @nicks = get_nicknames($e);
print  "<TD>" . join( ';', @nicks) . "</TD>\n";
print "<TD> <A href=/cgi-bin/kanjiinfo.pl?id=$e> ". $e . " </A></TD><TD><BIG>". get_char($e)." </BIG></TD>\n";

print "</TR>";
print "</TABLE> ";

print end_html;
