#!/bin/perl

# id:char:nicknames:subparts

my $data = <<'END_DATA';
rtk1:一:minus,one:: decom1 , decomp2 
rtk200:枠:frame:wood 90 9 10 , 十九 木
END_DATA
;;;


$table{'pipe'}{'char'}='xpipe';
$table{'pipe'}{'nicknames'}= ['vertical','stick'];


$table{'rtk1'}{'char'}='一';
$table{'rtk1'}{'nicknames'}= ['minus','one'];


$table{'rtk10'}{'char'}='x10';
$table{'rtk10'}{'nicknames'}= ['10','cross','plus'];
$table{'rtk10'}{'parts'}= [['minus', 'pipe']];



$table{'rtk-mouth'}{'char'}='xmouth';
$table{'rtk-mouth'}{'nicknames'}= ['box','square'];
$table{'rtk-mouth'}{'parts'}= [];


$table{'rtk-field'}{'char'}='xfield';
$table{'rtk-field'}{'nicknames'}= ['jail'];
$table{'rtk-field'}{'parts'}= [['mouth', 'plus'], ['box','10']];


#print "=> ". $table{'rtk1'}{'char'} ."\n";


#red @args; 

#for each arg: {
#  @expansion = expand($arg);
#  if ($first iteration) @result = @xpansion;
#  @result = overlap @expansion, @result
#}


sub get_nicknames 
{
  my $arg = @_[0];
  print "GN $arg \n";
  my $lstr = $table{$arg}{'nicknames'} ;
  my @L= @$lstr;
  print "nix " . join( ';', @L ) . "\n";
  return @L;
}


#return list of sub-parts of this kanji, if any... all decompositions are mixed together
#list may contain ids or nicknames
sub get_parts{
   my $entry = @_[0];  
   my $lstr = $table{$arg}{'parts'} ;
   my @L= @$lstr;
   my @res ;
   foreach $lref (@L) {
    print "parts " . join( ';', @$lref ) . "\n";
     push @res, @$lref;
   }
   return @res;
}

# check direct usage
#sabre is used in homecoming
sub is_part_used_in{
   my ($part,$entry) = @_;
   my $lstr = $table{$entry}{'parts'} ; #it is reference to list of lists of parts
   my @L= @$lstr;
   
   foreach my $lref (@L) {
      my @lst = @$lref;
      foreach  my $p (@lst) {
         if ($p eq $part) {
            return l;
         }
   }
   return 0;
}


