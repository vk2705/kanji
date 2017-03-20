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



my $data = $q->param('POSTDATA');
print "PD:$data" . " <hr> ";
if ($data=~ /char=(.*)/) {
    $data = $1;
} else {
    print "invalid form submitted\n";
    exit (0);
}

#    $v =  decode_entities($v);


###########

setup_tables();

my $n = decode_entities($data);

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
