#!/usr/bin/perl

##
##  printenv -- demo CGI program which just prints its environment
##

print "Content-type: text/plain\n\n";
foreach $var (sort(keys(%ENV))) {
    $val = $ENV{$var};
    $val =~ s|\n|\\n|g;
    $val =~ s|"|\\"|g;
    print "${var}=\"${val}\"\n";
}

use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);
use strict;

print header;
#print start_html("Thank You");
#print h2("Thank You");

my %form;
foreach my $p (param()) {
    $form{$p} = param($p);
    print "$p = $form{$p}\n";
}


