#!//usr/local/bin/perl -CS

use KanjiLookup;

setup_tables();
my@res = search_function(@ARGV);


#$table{$e}{'char'}
foreach my $e (@res) {
	print  $e . " ". get_char($e) ."\n";
}
