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


print " <BR>";

#do 'search.pl';
setup_tables();

my(%form);
my @q;
foreach my $p (param()) {
    my $v = param($p);
    $v =~ s/\s*$//; #cut ws
    $form{$p} = $v;
    my @l = get_amb_list ($v);
    if ($#l>0) {
	
	print "$v may mean one of following:<br>\n";
	my @ambig = get_amb_list ($v);
	foreach  my $v1 (@ambig) {
	    my $k = get_entry_by_nickname($v1);
	    my $c = 'undefined';
	    $c = show_char($k) if (defined $k) ;
	    $c = show_char($k) if (defined $k) ;
	    print "$v1 $k " .  $c   . "<BR>";
	}
	print "<HR>\n";
    }

 #print "$p --->  $form{$p}";
 push @q, $form{$p};
}


my@res = search_function(@q);

my $nres =  $#res +1;
print "found $nres results : <br> \n";
#print  join( ';', @res) ;

print "<TABLE BORDER=1>\n";
foreach my $e (@res) {

    

    print "<TR>\n";
    print  "<TD><A href=/cgi-bin/kanjiinfo.pl?id=$e> ". $e . " <BIG> ". show_char($e) ." </BIG> </A> </TD>\n";
    
    print  "<TD WIDTH=20>\n";
    my @nicks = get_nicknames($e);
    print  join( ';', @nicks) ;
    print  "</TD>\n";
    
    print  "<TD>\n";
    my @parts = get_parts($e);
    foreach my $p (@parts) {
	my $k = get_entry_by_nickname($p);
	print "<A href=/cgi-bin/kanjiinfo.pl?id=$k> ". $p . " </A> <BIG>". show_char($k)." </BIG>, \n";
    }
    print  "</TD>\n";
    
    print "</TR>\n";
}
print "</TABLE>\n";	

print end_html;
