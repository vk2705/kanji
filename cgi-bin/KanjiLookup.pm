#!/bin/perl -CS


package KanjiLookup;

use strict;
use Exporter;
use vars qw($VERSION @ISA @EXPORT @EXPORT_OK %EXPORT_TAGS);

$VERSION     = 1.00;
@ISA         = qw(Exporter);
@EXPORT      = qw(is_entry search_function setup_tables get_char get_nicknames get_parts get_entry_by_nickname get_amb_list get_by_substring get_by_char);
@EXPORT_OK   = qw(search_function setup_tables);
%EXPORT_TAGS = ( DEFAULT => [qw(&search_function)]);
				 

my %ambiguity;
my %table;
my %visually_similar;
my %semantically_similar;
my %lookup_by_nickname_table;
my %all_parts_table;
my %usage_table;

@visually_similar{'seven'}='spoon';
@visually_similar{'animal legs'}='infinity';

@semantically_similar{'tortoise'}=['turtle'];
@semantically_similar{'oneself'}=['I','self'];
#rob,burglar
#sign of the dragon,dragon

$ambiguity{going} =['rad3.33', 'rad6.23'];
$ambiguity{flesh}=['rad6.12', 'rad4.15'];
$ambiguity{'part of the body'}=['rad6.12', 'rad4.15'];
$ambiguity{'altar'} =['rad4.36', 'rad5.17'];
$ambiguity{'tripod'}= ['rad10.7','rad13.2'];
$ambiguity{'finger'}=['rtk711','rad3.34'];
$ambiguity{crown} = ['rtk326',"crown primitive"];
$ambiguity{head}=['rtk1549','head0'];
$ambiguity{wind}=['rad2.13','rad9.6'];
$ambiguity{ton}=['rtk2956','rad4.43'];
$ambiguity{nose}=['rad6.13','rtk733'];
$ambiguity{ceremony}=[ 'rad3.28','rtk1059'];
$ambiguity{saber}=[ 'rad2.16','rtk1801'];
$ambiguity{ball}=[ 'rtk1005','rtk272'];
$ambiguity{boulevard}=['rtk955', 'rad6.23'];
$ambiguity{house}=['rtk580', 'rad3.11'];
$ambiguity{finger}=['rtk711', 'rad3.34x'];
$ambiguity{second}=['rtk965', 'rad1.5','2nd'];
$ambiguity{saber}=['rtk1801', 'rad2.16'];
$ambiguity{nail}=['rtk2788', 'rtk95'];
$ambiguity{shape}=['rtk1847', 'rad3.32'];
$ambiguity{box}=['rtk1013', 'rad2.20'];
$ambiguity{desk}=['rad2.13', 'rtk223'];
$ambiguity{silver}=['rtk1569', 'rad6.18'];
$ambiguity{comb}=['rtk2542', 'rad6.8'];
$ambiguity{adjusted}=['rad8.12', 'rad14.2'];
$ambiguity{fist}=['rtk1290', 'rad2.30'];
$ambiguity{grass}=['wiki-rad2.9', 'rtk238'];
$ambiguity{stamp}=['rtk1530', 'rad2.23'];
$ambiguity{ladle}=['rtk72', 'rtk291'];
$ambiguity{umbrella}=['rad2.5', 'rtk1103'];
$ambiguity{eyeball}=['rtk1577', 'rad5.27'];
$ambiguity{again}=['rtk1956', 'rad2.26'];
$ambiguity{land}=['rad3.4', 'rtk1631'];
$ambiguity{tiger}=['rtk2145', 'rad6.20'];
$ambiguity{needle}=['rad2.21', 'rtk292'];
$ambiguity{seal}=['rtk168', 'rad2.23'];
$ambiguity{column}=['rad3.33', 'rtk1756'];
$ambiguity{going}=['rad3.33', 'rad6.23'];
$ambiguity{spirit}=['rtk2030', 'rad4.24'];
$ambiguity{'city walls'}=['rad3.40', 'rtk2296'];
$ambiguity{'embroidery'}=['rad12.2', 'rtk2707'];
$ambiguity{'fight'}=['rtk1757', 'rad10.5'];
$ambiguity{'cocoon'}=['rtk2025', 'rad3.24'];
$ambiguity{'oyster'}=['rad7.9', 'rtk2736'];
$ambiguity{'clam'}=['rad7.9', 'rtk2734'];
$ambiguity{'state of mind'}=['rad4.2', 'rad3.34'];
$ambiguity{elbow}=['rad2.25', 'rtk46'];
$ambiguity{private}=['rad2.25', 'rtk968'];
$ambiguity{flute}=['rtk1192', 'rad17'];
$ambiguity{cane}=['rtk2566', 'rad1.2'];
$ambiguity{outstanding}=['rtk2370', 'rad4.41'];
$ambiguity{ceremony}=['rad3.28', 'rtk1059'];
$ambiguity{ball}=['rtk1005', 'rtk272'];
$ambiguity{muscle}=['rad2.17', 'rtk1012'];
$ambiguity{negative}=['rad4.12', 'rtk1302'];
$ambiguity{slave}=['rad8.4', 'rtk2192'];
$ambiguity{flame}=['flame0','fire'];
$ambiguity{water}=['drops of water','water kanji'];
$ambiguity{eye}=['eyeball primitive','eye kanji'];
$ambiguity{ice}=['ice','ice2']; 
$ambiguity{'go in'}=['goin8','enter'];
$ambiguity{'shelf'}=['shelf0','shelf-kanji'];   
$ambiguity{'person'}=['hito','rad2.4'];   
$ambiguity{'crown'}= ['crown-kanji','crown0'];
$ambiguity{'flower'}= ['rtk1084','flower0'];

# add reflex processing
$visually_similar{"drag"}=["cliff"];
sub print_nicknames;
sub uniq;

sub dbg
{
	my ($s) = @_;
#	print $s;
}

#my $data = <<'END_DATA';
#rtk1:一:minus,one:: 
#rtk200:枠:frame:wood 90 9 10 , 十九 木
#END_DATA
#;;;

sub is_entry{
    my ($e) = @_;
    return 1 if (defined $table{$e});
    return 0;
}

sub get_char {
  my ($e) = @_;
  if (defined  $table{$e}) {
      return $table{$e}{'char'};
  } else {
      return "undef.char";
  }
}

my %entry_by_char;
sub nice_string {
    my $x = $_;

    join("",
	 map { $_ > 255                    # if wide character...
		   ? sprintf("\\{%04x}", $_)  # \x{...}
		   : chr($_) =~ /[[:cntrl:]]/  # else if control character...
		   ? sprintf("\\x%02X", $_)  # \x..
		   : quotemeta(chr($_))      # else quoted or as themselves
	       } unpack("W*", $_[0]));           # unpack Unicode characters

   
}

sub get_by_char {
    my ($e) = @_;
    return $entry_by_char{$e} if (defined $entry_by_char{$e});
}

sub add_to_list
{
	my($lref1, $lref2) = @_;
	#print "ALbef= " . join( ';', @$lref1 ) . "\n";
	push @{$lref1}, @$lref2;
	#print "ALaft= " . join( ';', @$lref1 ) . "\n";
	@{$lref1} = uniq (@{$lref1});
}

sub add_nickname
{
	my ($id, $nick) = @_;
	my $lr = $table{$id}{'nicknames'};
	#dbg "ANbef= " . join( ';', @$lr ) . "\n";
	push @{$lr}, $nick;
	#print "ANaft= " . join( ';', @$lr ) . "\n";
	@{$lr} = uniq @{$lr};
	#print_nicknames($id);
}
	

sub load_table {
  my $filename = 'data.txt';
  open(my $fh, '<:encoding(UTF-8)', $filename) or die "Could not open file '$filename' $!";
 # binmode $fh, ":utf8";
  while (my $row = <$fh>) {
      chomp $row;
      $row =~ s/\s+$//;
      $row = lc $row; #case insensitive
      next if $row =~ /#/;
      next if $row =~ /^(\s*?)$/;
      #print "$row\n";
      my @array = split /:/, $row;
      my $id = $array[0];
      my $char = $array[1];
      #print $char;
      my $nicks = $array[2];
      
      my $stories = $array[3] ;
      if (defined $entry_by_char{$char} and $char ne "?")  {
	  my $prev_id  = $entry_by_char{$char};
	  #print "merging $id --> $prev_id ($char)\n";
	  add_nickname($prev_id, $id);
	  $id = $prev_id;
      } else {
	  $entry_by_char{$char} = $id;
      }
      
      next if ($id eq "") ;
      
      $table{$id}{'char'}=$char;
      #print  ">>>>>>>>>>>>>>>$id<< ".$table{$id}{'char'} . "<BR>\n" if ($row =~/crown/);
      
      #foreach $nk (@nicks_lst) {
#	print "\t|$nk| "; 
#   }
#   print"\n";
      
      if(defined $nicks) {
	  my @nicks_lst = split /,/, $nicks;     
	  if (!defined $table{$id}{'nicknames'}) {
	      $table{$id}{'nicknames'} = \@nicks_lst;
	  } else {
	      add_to_list ($table{$id}{'nicknames'}, \@nicks_lst);
	  }
      }

      my @stories_list_of_lists ;	  
      if (defined $stories) {
	  my @stories_lst = split /;/, $stories; # stories separated by ;            
	  foreach my $story (@stories_lst) {
	      my @parts = split /,/, $story;
	      push   @stories_list_of_lists, \@parts;
	  }
	  if (!defined $table{$id}{'parts'}) {
	      $table{$id}{'parts'} = \@stories_list_of_lists;
	  } else {	      
	      add_to_list ( $table{$id}{'parts'} , \@stories_list_of_lists) ;
	  }
      }      
  }
  #dbg "load done\n";
}

#print "=> ". $table{'rtk1'}{'char'} ."\n";


#red @args; 

#for each arg: {
#  @expansion = expand($arg);
#  if ($first iteration) @result = @xpansion;
#  @result = overlap @expansion, @result
#}

sub uniq {
  my %seen;
  return grep { !$seen{$_}++ } @_;
}

sub get_by_substring
{
    my $arg = $_[0];
    my @res = ();

    return () unless defined $arg;

    foreach my $entry (all_entries_list()) {
	#print ("GBS $entry  \n");
	push @res, $entry if (index ($entry, $arg)>=0); 
	my @lst_nicks = get_nicknames($entry);
	foreach my $nick (@lst_nicks) {
	    push @res, $nick if (index ($nick,$arg) >=0); 
	}
    }
    return sort @res;
}

sub get_nicknames 
{
    my $arg = $_[0];
#    print "GN $arg \n";    
    my $lstr = $table{$arg}{'nicknames'} ;
    if (defined $lstr) {
	my @L= @$lstr;
	#print "nix " . join( ';', @L ) . "\n";
	return @L;
    } else {
	return ();
    }
}

sub print_nicknames
{
	my $arg = $_[0];
	my @L= get_nicknames($arg);
	print "nicknames of $arg :" . join( ';', @L ) . "\n";	
}

#return list of sub-parts of this kanji, if any... all decompositions are mixed together
#list may contain ids or nicknames
sub get_parts{
   my $entry = $_[0];  
   if (!defined $_[0]) {
	die "get_parts error : undef	param\n";
   }
   if (!defined $table{$entry}) {
       return ();
   }
   
   my $lstr = $table{$entry}{'parts'} ;
   
   if (! defined $table{$entry}{'parts'}) {
       #die "get_parts error : undef parts for $entry\n";
       return ();
   }
   
   my @L= @$lstr;
   my @res ;
   #print "GP $entry\n";
   
   foreach my $lref (@L) {
    #print "parts " . join( ';', @$lref ) . "\n";
     push @res, @$lref;
   }
   return @res;
}



sub get_entry_by_nickname
{
  #or by name
  #- build in advance hash nickname -> entry name
  my ($nick) = @_;
  if (defined($table{$nick})) {
      return $nick;
  }
#  print ("get_entry_by_nickname check lookup_by_nickname_table $nick \n");
  return  $lookup_by_nickname_table{$nick};
}

sub all_entries_list 
{
  return (keys %table);
}

sub build_lookup_by_nickname_table 
{
    my $ret = 1;
    foreach my $entry (all_entries_list()) {
	my @lst_nicks = get_nicknames($entry);
	foreach my $nick (@lst_nicks) {
	    if (defined $lookup_by_nickname_table{$nick})  {
		#printf "Double nick: $nick $entry  $lookup_by_nickname_table{$nick} \n";
		#exit(1);
		my $second = $lookup_by_nickname_table{$nick};

		if (defined $table{$second}) {
		
		    if ($table{$entry}{'char'} eq $table{$second}{'char'}) {
			printf "Double nick same char: $nick $entry  $lookup_by_nickname_table{$nick} \n";
			$ret = 0;
			next;
		    }
		}
		my $second = $lookup_by_nickname_table{$nick};		     
		printf "Double nick: $nick $entry $table{$entry}{char}  $second $table{$second}{char}\n";
		$ret = 0;
		print '$ambiguity'."{$nick}=['$entry', '$lookup_by_nickname_table{$nick}']; \n\n";
		
	    }
        $lookup_by_nickname_table{$nick} = $entry;
      }
  }
  if (!$ret) {
   printf ("exit at build_lookup_by_nickname_table\n");
	exit 1 ;
  }
}
 
my $errors = 0;
sub get_all_parts
{
       my ($entry)= @_;
    #   print "called get_all_parts of $entry\n";
       
       return "" unless ($entry ne "");
       my $id =  get_entry_by_nickname($entry);
	   if (!defined $id) {
			##################### 
			die "processing \"$entry\" : undefined \n";
			$errors ++;
			return();
		}
	   
	
       my @lst = get_parts($id);
#	   print "===parts " . join( ';', @lst ) . "\n";
       my @res;
       foreach my $part (@lst) {
	     if ($part eq $entry) {
				die "get_all_parts: loop $entry consists of itself ";
				exit(1);
			}
			
         my @ap = get_all_parts($part);
         push @res, @ap;
         push @res, $part;
       } 
       return uniq (@res);
} 

sub  build_all_parts_table {
    foreach my $entry  (sort keys %table) {
	die if (!defined $entry);
	next if ( $entry eq "" );
	dbg(" build_all_parts_table $entry \n");
	my @all_parts = get_all_parts ($entry);
	dbg("\n----\n");
	$all_parts_table{$entry} = @all_parts;
	foreach my $part (@all_parts) {
	    if ($part eq $entry) {
		print "build_all_parts_table: loop \"$entry\" consists of itself ";
		exit(1);
	    }
#            print ("ADD USG $part,$entry\n");
	    my $canonic_name = get_entry_by_nickname($part);
	    if (!defined $canonic_name) {
#		die "undefined canonic name for \"$part\" \n"; 
		next;
	    }

	    $usage_table{$canonic_name}{$entry} = 1;
	}
    }  
} 


sub get_users_of {
   my ($e)= @_;
   return if ($e eq ""); 
  
   my $name = get_entry_by_nickname($e);
#   print "Lookup/get_users_of: |$name|\n";
   return if ($name eq ""); 
  
   return (keys %{  $usage_table{$name} });
}

sub intersection {
  my @parts = @_;
  my $num = @parts;
  
  my %inter;
  
  #print "Inter num = $num\n";
  foreach my $part (@parts) {
    my @users = get_users_of ($part);
    push @users, $part;
    foreach my $u (@users) {
      $inter{$u} ++;
    }  
  } 
  
  my @res;
  foreach my $u (keys %inter) {
    #print "inter $u ? " . $inter{$u} ."\n";
    push (@res, $u) if ($inter{$u}== $num);
  }
  return @res;
}



sub get_amb_list 
{
	my ($n) = (@_);
	return ($n) unless (defined $ambiguity{$n});
	my $lref = $ambiguity{$n};
	return @{$lref};
}

 
sub search_function
{
	my @ARGV=@_;	 
	#get_amb_list	
	my $numargs = @ARGV;
	my @ambig1 = ("");
	my @ambig2 = ("");
	my @ambig3 = ("");
	my @ambig4 = ("");
	my @ambig5 = ("");
	my @ambig6 = ("");
	
	@ambig1 = get_amb_list (lc $ARGV[0])  if ($numargs >0);
	@ambig2 = get_amb_list (lc $ARGV[1])  if ($numargs >1);
	@ambig3 = get_amb_list (lc $ARGV[2])  if ($numargs >2);

	my %ret;
	
	foreach  my $v1 (@ambig1) {
	 foreach  my $v2 (@ambig2) { 
	  foreach  my $v3 (@ambig3)  {
		#print " RUN: $v1, $v2, $v3\n"	  ;
	  
		my @params;
		push @params, get_entry_by_nickname($v1) if ($v1 ne ""); 
		push @params, get_entry_by_nickname($v2) if ($v2 ne ""); 
		push @params, get_entry_by_nickname($v3) if ($v3 ne ""); 
		
		#print "DBG $v1 -> " .  get_entry_by_nickname($v1)  ."\n";
		  
		#print "RESULTS:=============\n";
		foreach my $e (intersection(@params)) {
			$ret{$e}=1;
			#print  $e . " ". $table{$e}{'char'} ."\n";
		}
		#print "RES:" . join( ';', intersection(@ARGV) ) ."\n";

	  }
	 }
	}
	return (keys %ret);
}  
 
 sub setup_tables 
 {
   load_table ();
   build_lookup_by_nickname_table();
   dbg "build_all_parts_table\n";
   build_all_parts_table();
   #print "$errors errors\n";
 }
 
1;
