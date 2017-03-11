#!/usr/bin/perl
open my $fh, "<:encoding(UTF-8)", 'data.txt';


use open ':std', ':encoding(utf-8)';
while (<$fh>) {
    if (/^(.)/) {
        print "Your kanji is '$1'.\n";
    }
}
close $fh;

my $alert = 'The radioactive snowmen come in peace: ? ??? ?';
print $alert;