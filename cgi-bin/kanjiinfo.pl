#!/usr/local/bin/perl -w -CS
use lib '/var/www/cgi-bin';

use strict;
use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);

use KanjiLookup;

sub show_char{
    my $x = shift;
    my $c = get_char($x);
    if ($c =~ /png/) {
	return "<IMG height=\"20\" width=\"20\" SRC=/kanji-pics/$c>"; 
    } else {
	return $c; 
    }
} 

my $q = CGI->new();

print $q->header( -charset=> "utf-8" ) ;
#print start_html("Environment");

print "<html lang=\"ja\">\n";

#foreach my $key (sort(keys(%ENV))) {
#    print "$key = $ENV{$key}<br>\n";
#}

#print " <BR>";

my(%form);
#my @q;
foreach my $p (param()) {
    $form{$p} = param($p);

#    print "$p --->  $form{$p}";
#    push @q, $form{$p};
}

#do 'search.pl';
setup_tables();
#my@res = search_function(@q);



print "<BIG>\n";
print "</BIG>\n";	

# print "<TABLE BORDER=1>\n";
my $n = $form{id};
my $e = get_entry_by_nickname($n);

print "Kanji <BR>\n";
print  "id:". $e . "   <BIG> ". show_char($e) ." </BIG>  <BR>\n";

print  "Nicknames: <br>";
my @nicks = get_nicknames($e);
print  join( ';', @nicks) . "<BR>\n";


print  "Parts: <BR>\n";
my @parts = get_parts($e);
foreach my $pt (@parts) {
    my $k = get_entry_by_nickname($pt);
    my $escaped_k = escapeHTML($k);
    print "<A href=/cgi-bin/kanjiinfo.pl?id=$escaped_k> ". $pt . " </A> <BIG>". get_char($k)." </BIG>, \n";
}
print  "</TD>\n";

print "</TR>\n";

#print "</TABLE>\n";	



print end_html;
