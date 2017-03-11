#!/usr/local/bin/perl -w -CS
use lib '/var/www/cgi-bin';

use strict;
use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);


use KanjiLookup;


my $q = CGI->new();

print $q->header( -charset=> "utf-8" ) ;

print "<html lang=\"ja\">\n";

my(%form);

foreach my $p (param()) {
    my $v = param($p);
    $v =~ s/\s+$//;
    $form{$p} = $v;    
}

setup_tables();

my $n = $form{substring};

die "undef param substring!\n" if (!defined $n) ;

print "SEARCH PARAMETER: $n </BR>\n";

my @lst = get_by_substring($n);


#print  join( ';', @lst) . "<BR>\n";
print "<TABLE BORDER=1> <TH>Alternative names</TH> <TH>Id</TH> <TH>Kanji</TH>  \n";
my %was;
foreach my $x (@lst) {
    print "<TR>";
    #print "<TD> $x </TD>";
    my $e = get_entry_by_nickname($x);
    next if ($was{$e}); $was{$e} = 1;
   
    my @nicks = get_nicknames($e);
    print  "<TD>" . join( ';', @nicks) . "</TD>\n";

    print "<TD> <A href=/cgi-bin/kanjiinfo.pl?id=$e> ". $e . " </A></TD><TD><BIG>". get_char($e)." </BIG></TD>\n";
    print "</TR>";
}
print "</TABLE> ";

print end_html;
