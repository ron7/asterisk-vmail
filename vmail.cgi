#!/usr/bin/perl
#use strict;
#use warnings;
#
# Web based Voicemail for Asterisk
#
# Copyright (C) 2002, Linux Support Services, Inc.
#
# Distributed under the terms of the GNU General Public License
#
# Written by Mark Spencer <markster@linux-support.net>
#
# (icky, I know....  if you know better perl please help!)
#
#
# Synchronization added by GDS Partners (www.gdspartners.com)
#			 Stojan Sljivic (stojan.sljivic@gdspartners.com)
#
use CGI qw/:standard/;
use Carp::Heavy;
use CGI::Carp qw(fatalsToBrowser);
use DBI;
#use Fcntl qw ( O_WRONLY O_CREAT O_EXCL );
use Fcntl;
use Time::HiRes qw ( usleep );

my $context=""; # Define here your by default context (so you dont need to put voicemail@context in the login)

my @validfolders = ( "INBOX", "Old", "Work", "Family", "Friends", "Cust1", "Cust2", "Cust3", "Cust4", "Cust5" );

my %formats = (
  "wav" => {
    name => "Uncompressed WAV",
    mime => "audio/wav",
    pref => 1
  },
  "WAV" => {
    name => "GSM Compressed WAV",
    mime => "audio/wav",
    pref => 2
  },
  "gsm" => {
    name => "Raw GSM Audio",
    mime => "audio/x-gsm",
    pref => 3
  }
);

my $astpath = "/_asterisk";

my $stdcontainerstart = "";
my $footer = "<p></p><footer class='text-center'><font size=-1><a href=\"http://www.asterisk.org\">The Asterisk Open Source PBX</a> Copyright 2004-2008, <a href=\"http://www.digium.com\">Digium, Inc.</a>, UI improved by <a href='//xron.net/' target='_blank'>Xron.net</a> 2018</footer>";
my $stdcontainerend = "$footer</div> <script src='https://cdnjs.cloudflare.com/ajax/libs/jquery/3.3.1/jquery.min.js'></script> <script> \$('#checkall').on('click',function(){ \$( 'input:checkbox' ).not(this).prop('checked',this.checked); }); </script> </body>\n";

sub html_header($) {
  my($title) = @_;

  return "<html>
  <head>
  <title>$title</title>
  <link href='https://stackpath.bootstrapcdn.com/bootstrap/4.1.0/css/bootstrap.min.css' rel='stylesheet' integrity='sha384-9gVQ4dYFwwWSjIDZnLEWnxCjeSWFphJiwGPXr1jddIhOegiu1FwO5qRGvFXOdJZ4' crossorigin='anonymous'>
  <style>
  body { margin-top:30px; }
  * { font-size:14px; }
  </style>
  </head>
  <body>
  <div class='container'>
  ";
}

sub lock_path($) {

  my($path) = @_;
  my $rand;
  my $rfile;
  my $start;
  my $res;

  $rand = rand 99999999;	

  $rfile = "$path/.lock-$rand";

  sysopen(RFILE, $rfile, O_WRONLY | O_CREAT | O_EXCL, 0666) or die "sysopen: $!";
  close(RFILE) or die "close: $!";

  $res = link($rfile, "$path/.lock");
  $start = time;
  if ($res == 0) {
    while (($res == 0) && (time - $start <= 5)) {
      $res = link($rfile, "$path/.lock");
      usleep(1);
    }
  }
  unlink($rfile);

  if ($res == 0) {
    die "die $!";
  } else {
    return 0;
  }
}

sub unlock_path($) {

  my($path) = @_;

  unlink("$path/.lock");
}

sub untaint($) {

  my($data) = @_;

  if ($data =~ /^([-\@\w.]+)$/) {
    $data = $1;
  } else {
    die "Security violation.";
  }

  return $data;
}

sub login_screen($) {
  print header;
  my ($message) = @_;
  print html_header("Asterisk Web-Voicemail");
  print <<_EOH;
  $stdcontainerstart
  $message
  <div class="row justify-content-md-center">
    <div class="col-6">
<form method="post">
<h5 class='text-center'>Voice Mail Login</h5>
<input type=hidden name="action" value="login">
<input type=hidden name="context" value="$context">

  <div class="form-group row">
    <label for="staticMailbox" class="col-sm-4 col-form-label">Mailbox</label>
    <div class="col-sm-8">
      <input type="text" name="mailbox" autofocus class="form-control" id="staticMailbox" value="">
    </div>
  </div>
  <div class="form-group row">
    <label for="inputPassword" class="col-sm-4 col-form-label">Password</label>
    <div class="col-sm-8">
      <input type="password" name="password" class="form-control" id="inputPassword" placeholder="Password">
    </div>
  </div>
  <div class="form-group row">
    <div class="col-sm-8 offset-sm-4">
      <button type="submit" class="btn-block btn btn-sm btn-success">Login</button>
    </div>
  </div>

</form>
    </div>
    $stdcontainerend
_EOH

}

sub check_login($$)
{
  my ($filename, $startcat) = @_;
  my ($mbox, $context) = split(/\@/, param('mailbox'));
  my $pass = param('password');
  my $category = $startcat;
  my @fields;
  my $tmp;
  local (*VMAIL);
  if (!$category) {
    $category = "general";
  }
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }
  if (!$filename) {
    $filename = "/etc/asterisk/voicemail.conf";
  }
#	print header;
#	print "Including <h2>$filename</h2> while in <h2>$category</h2>...\n";
  open(VMAIL, "<$filename") || die("Bleh, no $filename");
  while(<VMAIL>) {
    chomp;
    if (/include\s\"([^\"]+)\"$/) {
      ($tmp, $category) = &check_login("/etc/asterisk/$1", $category);
      if (length($tmp)) {
#				print "Got '$tmp'\n";
        return ($tmp, $category);
      }
    } elsif (/\[(.*)\]/) {
      $category = $1;
    } elsif ($category eq "general") {
      if (/([^\s]+)\s*\=\s*(.*)/) {
        if ($1 eq "dbname") {
          $dbname = $2;
        } elsif ($1 eq "dbpass") {
          $dbpass = $2;
        } elsif ($1 eq "dbhost") {
          $dbhost = $2;
        } elsif ($1 eq "dbuser") {
          $dbuser = $2;
        }
      }
      if ($dbname and $dbpass and $dbhost and $dbuser) {

        # db variables are present.  Use db for authentication.
        my $dbh = DBI->connect("DBI:mysql:$dbname:$dbhost",$dbuser,$dbpass);
        my $sth = $dbh->prepare(qq{select fullname,context from voicemail where mailbox='$mbox' and password='$pass' and context='$context'});
        $sth->execute();
        if (($fullname, $category) = $sth->fetchrow_array()) {
          return ($fullname ? $fullname : "Extension $mbox in $context",$category);
        }
      }
    } elsif (($category ne "general") && ($category ne "zonemessages")) { 
      if (/([^\s]+)\s*\=\>?\s*(.*)/) {
        @fields = split(/\,\s*/, $2);
#				print "<p>Mailbox is $1\n";
        if (($mbox eq $1) && (($pass eq $fields[0]) || ("-${pass}" eq $fields[0])) && ($context eq $category)) {
          return ($fields[1] ? $fields[1] : "Extension $mbox in $context", $category);
        }
      }
    }
  }
  close(VMAIL);
  return ("", $category);
}

sub validmailbox($$$$)
{
  my ($context, $mbox, $filename, $startcat) = @_;
  my $category = $startcat;
  my @fields;
  local (*VMAIL);
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }
  if (!$filename) {
    $filename = "/etc/asterisk/voicemail.conf";
  }
  if (!$category) {
    $category = "general";
  }
  open(VMAIL, "<$filename") || die("Bleh, no $filename");
  while (<VMAIL>) {
    chomp;
    if (/include\s\"([^\"]+)\"$/) {
      ($tmp, $category) = &validmailbox($mbox, $context, "/etc/asterisk/$1");
      if ($tmp) {
        return ($tmp, $category);
      }
    } elsif (/\[(.*)\]/) {
      $category = $1;
    } elsif ($category eq "general") {
      if (/([^\s]+)\s*\=\s*(.*)/) {
        if ($1 eq "dbname") {
          $dbname = $2;
        } elsif ($1 eq "dbpass") {
          $dbpass = $2;
        } elsif ($1 eq "dbhost") {
          $dbhost = $2;
        } elsif ($1 eq "dbuser") {
          $dbuser = $2;
        }
      }
      if ($dbname and $dbpass and $dbhost and $dbuser) {

        # db variables are present.  Use db for authentication.
        my $dbh = DBI->connect("DBI:mysql:$dbname:$dbhost",$dbuser,$dbpass);
        my $sth = $dbh->prepare(qq{select fullname,context from voicemail where mailbox='$mbox' and password='$pass' and context='$context'});
        $sth->execute();
        if (($fullname, $context) = $sth->fetchrow_array()) {
          return ($fullname ? $fullname : "unknown", $category);
        }
      }
    } elsif (($category ne "general") && ($category ne "zonemessages") && ($category eq $context)) {
      if (/([^\s]+)\s*\=\>?\s*(.*)/) {
        @fields = split(/\,\s*/, $2);
        if (($mbox eq $1) && ($context eq $category)) {
          return ($fields[2] ? $fields[2] : "unknown", $category);
        }
      }
    }
  }
  return ("", $category);
}

sub mailbox_options()
{
  my ($context, $current, $filename, $category) = @_;
  local (*VMAIL);
  my $tmp2;
  my $tmp;
  if (!$filename) {
    $filename = "/etc/asterisk/voicemail.conf";
  }
  if (!$category) {
    $category = "general";
  }
#	print header;
#	print "Including <h2>$filename</h2> while in <h2>$category</h2>...\n";
  open(VMAIL, "<$filename") || die("Bleh, no voicemail.conf");
  while(<VMAIL>) {
    chomp;
    s/\;.*$//;
    if (/include\s\"([^\"]+)\"$/) {
      ($tmp2, $category) = &mailbox_options($context, $current, "/etc/asterisk/$1", $category);
#			print "Got '$tmp2'...\n";
      $tmp .= $tmp2;
    } elsif (/\[(.*)\]/) {
      $category = $1;
    } elsif ($category eq "general") {
      if (/([^\s]+)\s*\=\s*(.*)/) {
        if ($1 eq "dbname") {
          $dbname = $2;
        } elsif ($1 eq "dbpass") {
          $dbpass = $2;
        } elsif ($1 eq "dbhost") {
          $dbhost = $2;
        } elsif ($1 eq "dbuser") {
          $dbuser = $2;
        }
      }
      if ($dbname and $dbpass and $dbhost and $dbuser) {

        # db variables are present.  Use db for authentication.
        my $dbh = DBI->connect("DBI:mysql:$dbname:$dbhost",$dbuser,$dbpass);
        my $sth = $dbh->prepare(qq{select mailbox,fullname,context from voicemail where context='$context' order by mailbox});
        $sth->execute();
        while (($mailbox, $fullname, $category) = $sth->fetchrow_array()) {
          $text = $mailbox;
          if ($fullname) {
            $text .= " (".$fullname.")";
          }
          if ($mailbox eq $current) {
            $tmp .= "<option selected>$text</option>\n";
          } else {
            $tmp .= "<option>$text</option>\n";
          }
        }
        return ($tmp, $category);
      }
    } elsif (($category ne "general") && ($category ne "zonemessages")) {
      if (/([^\s]+)\s*\=\>?\s*(.*)/) {
        @fields = split(/\,\s*/, $2);
        $text = "$1";
        if ($fields[1]) {
          $text .= " ($fields[1])";
        }
        if ($1 eq $current) {
          $tmp .= "<option selected>$text</option>\n";
        } else {
          $tmp .= "<option>$text</option>\n";
        }

      }
    }
  }
  close(VMAIL);
  return ($tmp, $category);
}

sub mailbox_list()
{
  my ($name, $context, $current) = @_;
  my $tmp;
  my $text;
  my $tmp;
  my $opts;
  if (!$context) {
    $context = "default";
  }
  $tmp = "<select class='form-control' style='width:260px;display:inline;' name=\"$name\">\n";
  ($opts) = &mailbox_options($context, $current);
  $tmp .= $opts;
  $tmp .= "</select>\n";

}

sub msgcount() 
{
  my ($context, $mailbox, $folder) = @_;
  my $path = "/var/spool/asterisk/voicemail/$context/$mailbox/$folder";
  if (opendir(DIR, $path)) {
    my @msgs = grep(/^msg....\.txt$/, readdir(DIR));
    closedir(DIR);
    return sprintf "%d", $#msgs + 1;
  }
  return "0";
}

sub msgcountstr()
{
  my ($context, $mailbox, $folder) = @_;
  my $count = &msgcount($context, $mailbox, $folder);
  if ($count > 1) {
    "$count messages";
  } elsif ($count > 0) {
    "$count message";
  } else {
    "no messages";
  }
}
sub messages()
{
  my ($context, $mailbox, $folder) = @_;
  my $path = "/var/spool/asterisk/voicemail/$context/$mailbox/$folder";
  if (opendir(DIR, $path)) {
    my @msgs = sort grep(/^msg....\.txt$/, readdir(DIR));
    closedir(DIR);
    return map { s/^msg(....)\.txt$/$1/; $_ } @msgs;
  }
  return ();
}

sub getcookie()
{
  my ($var) = @_;
  return cookie($var);
}

sub makecookie()
{
  my ($format) = @_;
  cookie(-name => "format", -value =>["$format"], -expires=>"+1y");
}

sub getfields()
{
  my ($context, $mailbox, $folder, $msg) = @_;
  my $fields;
  if (open(MSG, "</var/spool/asterisk/voicemail/$context/$mailbox/$folder/msg${msg}.txt")) {
    while(<MSG>) {
      s/\#.*$//g;
      if (/^(\w+)\s*\=\s*(.*)$/) {
        $fields->{$1} = $2;
      }
    }
    close(MSG);
    $fields->{'msgid'} = $msg;
  } else { print "<BR>Unable to open '$msg' in '$mailbox', '$folder'\n<B>"; }
  $fields;
}

sub message_prefs()
{
  my ($nextaction, $msgid) = @_;
  my $folder = param('folder');
  my $mbox = param('mailbox');
  my $context = param('context');
  my $passwd = param('password');
  my $format = param('format');
  if (!$format) {
    $format = &getcookie('format');
  }
  print header;
  print html_header("Asterisk Web-Voicemail: Preferences");
  print <<_EOH;
  $stdcontainerstart
  <h5>Web Voicemail Preferences</h5>
<FORM METHOD="post" class='form-control'>
<p>Preferred Audio Format:</p>
_EOH

  foreach $fmt (sort { $formats{$a}->{'pref'} <=> $formats{$b}->{'pref'} } keys %formats) {
    my $clicked = "checked" if $fmt eq $format;
    print "<div class='radio'><label><input type=radio name=\"format\" $clicked value=\"$fmt\" class='forn-control'> $formats{$fmt}->{name}</label></div>";
  }

  print <<_EOH;
<input type=submit value="save settings..." class='btn btn-sm btn-success'>
<input type=hidden name="action" value="$nextaction">
<input type=hidden name="folder" value="$folder">
<input type=hidden name="mailbox" value="$mbox">
<input type=hidden name="context" value="$context">
<input type=hidden name="password" value="$passwd">
<input type=hidden name="msgid" value="$msgid">
$stdcontainerend
_EOH

}

sub message_play()
{
  my ($message, $msgid) = @_;
  my $folder = param('folder');
  my ($mbox, $context) = split(/\@/, param('mailbox'));
  my $passwd = param('password');
  my $format = param('format');

  my $fields;
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }

  my $folders = &folder_list('newfolder', $context, $mbox, $folder);
  my $mailboxes = &mailbox_list('forwardto', $context, $mbox);
  if (!$format) {
    $format = &getcookie('format');
  }
  if (!$format) {
    &message_prefs("play", $msgid);
  } else {
    print header(-cookie => &makecookie($format));
    $fields = &getfields($context, $mbox, $folder, $msgid);
    if (!$fields) {
      print "<BR>Bah!\n";
      return;
    }
    my $duration = $fields->{'duration'};
    if ($duration) {
      $duration = sprintf "%d:%02d", $duration/60, $duration % 60; 
    } else {
      $duration = "<i>Unknown</i>";
    }
    print html_header("Asterisk Web-Voicemail: $folder Message $msgid");
    print <<_EOH;
    $stdcontainerstart
<FORM METHOD="post">
<table class="table table-concise table-striped" width=100% align=center>
  <tr><td colspan=2 align=center><font size=+1>$folder <b> Message: $msgid</b></font></td></tr>
  <!--tr><td><b>Message:</b></td><td>$msgid</td></tr-->
  <!--tr><td><b>Mailbox:</b></td><td>$mbox\@$context</td></tr-->
  <tr><td><b>Folder:</b></td><td>$folder</td></tr>
  <tr><td><b>From:</b></td><td>$fields->{callerid}</td></tr>
  <tr><td><b>Duration:</b></td><td>$duration</td></tr>
  <tr><td><b>Original Date:</b></td><td>$fields->{origdate}</td></tr>
  <tr><td><b>Original Mailbox:</b></td><td>$fields->{origmailbox}</td></tr>
  <tr><td><b>Caller Channel:</b></td><td>$fields->{callerchan}</td></tr>
  <tr><td align=center colspan=2>
  <input name="action" type=submit value="index" class="btn btn-sm btn-info"> 
  <input name="action" type=submit value="delete " class="btn btn-sm btn-danger"> 
  <input name="action" type=submit value="forward to -> " class="btn btn-sm btn-info"> 
  $mailboxes 
  <input name="action" type=submit value="save to ->" class="btn btn-sm btn-info">
  $folders 
  <input name="action" type=submit value="play " class="btn btn-sm btn-info">
  <input name="action" type=submit value="download" class="btn btn-sm btn-info">
</td></tr>
<tr><td colspan=2 align=center>
<embed width=500 height=160 src="vmail.cgi?action=audio&folder=$folder&mailbox=$mbox&context=$context&password=$passwd&msgid=$msgid&format=$format&dontcasheme=$$.$format" autostart=yes loop=false></embed>
</table>
<input type=hidden name="folder" value="$folder">
<input type=hidden name="mailbox" value="$mbox">
<input type=hidden name="context" value="$context">
<input type=hidden name="password" value="$passwd">
<input type=hidden name="msgid" value="$msgid">
$stdcontainerend
_EOH
  }
}

sub message_audio()
{
  my ($forcedownload) = @_;
  my $folder = &untaint(param('folder'));
  my $msgid = &untaint(param('msgid'));
  my $mailbox = &untaint(param('mailbox'));
  my $context = &untaint(param('context'));
  my $format = param('format');
  if (!$format) {
    $format = &getcookie('format');
  }
  &untaint($format);

  my $path = "/var/spool/asterisk/voicemail/$context/$mailbox/$folder/msg${msgid}.$format";

  $msgid =~ /^\d\d\d\d$/ || die("Msgid Liar ($msgid)!");
  grep(/^${format}$/, keys %formats) || die("Format Liar ($format)!");

  # Mailbox and folder are already verified
  if (open(AUDIO, "<$path")) {
    $size = -s $path;
    $|=1;
    if ($forcedownload) {
      print header(-type=>$formats{$format}->{'mime'}, -Content_length => $size, -attachment => "msg${msgid}.$format");
    } else {		
      print header(-type=>$formats{$format}->{'mime'}, -Content_length => $size);
    }

    while(($amt = sysread(AUDIO, $data, 4096)) > 0) {
      syswrite(STDOUT, $data, $amt);
    }
    close(AUDIO);
  } else {
    die("Hrm, can't seem to open $path\n");
  }
}

sub message_index() 
{
  my ($folder, $message) = @_;
  my ($mbox, $context) = split(/\@/, param('mailbox'));
  my $passwd = param('password');
  my $message2;
  my $msgcount;	
  my $hasmsg;
  my ($newmessages, $oldmessages);
  my $format = param('format');
  if (!$format) {
    $format = &getcookie('format');
  }
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }
  if ($folder) {
    $msgcount = &msgcountstr($context, $mbox, $folder);
    $message2 = "<h5>Folder '$folder' has " . &msgcountstr($context, $mbox, $folder) . "</h5>";
  } else {
    $newmessages = &msgcount($context, $mbox, "INBOX");
    $oldmessages = &msgcount($context, $mbox, "Old");
    if (($newmessages > 0) || ($oldmessages < 1)) {
      $folder = "INBOX";
    } else {
      $folder = "Old";
    }
    $message2 = "You have";
    if ($newmessages > 0) {
      $message2 .= " <b>$newmessages</b> NEW";
      if ($oldmessages > 0) {
        $message2 .= "and <b>$oldmessages</b> OLD";
        if ($oldmessages != 1) {
          $message2 .= " messages.";
        } else {
          $message2 .= "message.";
        }
      } else {
        if ($newmessages != 1) {
          $message2 .= " messages.";
        } else {
          $message2 .= " message.";
        }
      }
    } else {
      if ($oldmessages > 0) {
        $message2 .= " <b>$oldmessages</b> OLD";
        if ($oldmessages != 1) {
          $message2 .= " messages.";
        } else {
          $message2 .= " message.";
        }
      } else {
        $message2 .= " <b>no</b> messages.";
      }
    }
  }

  my $folders = &folder_list('newfolder', $context, $mbox, $folder);
  my $cfolders = &folder_list('changefolder', $context, $mbox, $folder);
  my $mailboxes = &mailbox_list('forwardto', $context, $mbox);
  print header(-cookie => &makecookie($format));
  print html_header("Asterisk Web-Voicemail: $mbox\@$context $folder");
  print <<_EOH;
  $stdcontainerstart
<h4 class='text-center'>$message</h4>

<h5>$message2</h5>
<FORM METHOD="post">
<div class='text-right'><font size=+1><b>$folder</b> Messages</font> <input class="btn btn-sm btn-info" type=submit name="action" value="change to ->"> $cfolders</div>
<table class="table table-concise table-striped" width=100% align=center cellpadding=0 cellspacing=0>
_EOH

  print "<tr><th><input type=checkbox id='checkall'> Msg</th><th>From</th><th>Duration</th><th>Date</th><th></th></tr>\n";
  foreach $msg (&messages($context, $mbox, $folder)) {

    $fields = &getfields($context, $mbox, $folder, $msg);
    $duration = $fields->{'duration'};
    if ($duration) {
      $duration = sprintf "%d:%02d", $duration / 60, $duration % 60;
    } else {
      $duration = "<i>Unknown</i>";
    }
    $hasmsg++;
    print "<tr><td><input type=checkbox name=\"msgselect\" value=\"$msg\"> <b>$msg</b></td><td>$fields->{'callerid'}</td><td>$duration</td><td>$fields->{'origdate'}</td><td><input name='play$msg' alt=\"Play message $msg\" border=0 type=image align=left src=\"data:image/png;base64, iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABBklEQVQ4jaXTMUqDQRAF4O+3s5GIlQQsE1JIUnkGISLa2Vh4DCtvksJCSBG00UPYKAhKUgWDOUZisRNYw78RdGCbN/PeG2Zm+WdUBbyLM7SwxAT3ePtNcA+jIE3xEG8a2BC7m8jvUXxck+/jM7po1AmMgry/ocMmZrhbT3Sjxdz5BJc1IqdYoJODN+Gex0WIDrCd4RW+cA1bAbbwWmj7Cs+Z4zJq27nAskAuRbXirAQm6BWKBzjCR0buYZwXHYZiP8NKQzyXhtheTwylPTc3tH6AOW7rkrvSkcykVeVnXoXzHC/YKTk0pCNZSKt6xFMQF+H8g1z6TB3pM7Wl2YylzzQu1P89vgHVqjn/0r7QjAAAAABJRU5ErkJggg==\"></td></tr>\n";

  }
  if (!$hasmsg) {
    print "<tr><td colspan=4 align=center><P><b><i>No messages</i></b><P></td></tr>";
  }

  print <<_EOH;
</table>
<table width=100% align=center>
<tr><td align=right colspan=2>
  <input type="submit" name="action" value="refresh" class="btn btn-sm btn-info"> 
_EOH

  if ($hasmsg) {
    print <<_EOH;
  <input type="submit" name="action" value="delete" class="btn btn-sm btn-danger"> 
  <input type="submit" name="action" value="save to ->" class="btn btn-sm btn-info">
  $folders 
  <input type="submit" name="action" value="forward to ->" class="btn btn-sm btn-info">
  $mailboxes
_EOH
  }

  print <<_EOH;
</td></tr>
<tr><td align=right colspan=2>
  <input type="submit" name="action" value="preferences" class="btn btn-sm btn-primary">
  <input type="submit" name="action" value="logout" class="btn btn-sm btn-danger">
</td></tr>
</table>
<input type=hidden name="folder" value="$folder">
<input type=hidden name="mailbox" value="$mbox">
<input type=hidden name="context" value="$context">
<input type=hidden name="password" value="$passwd">
</FORM>
$stdcontainerend
_EOH
}

sub validfolder()
{
  my ($folder) = @_;
  return grep(/^$folder$/, @validfolders);
}

sub folder_list()
{
  my ($name, $context, $mbox, $selected) = @_;
  my $f;
  my $count;
  my $tmp = "<select class='form-control' style='width:200px;display:inline;' name=\"$name\">\n";
  foreach $f (@validfolders) {
    $count =  &msgcount($context, $mbox, $f);
    if ($f eq $selected) {
      $tmp .= "<option selected>$f ($count)</option>\n";
    } else {
      $tmp .= "<option>$f ($count)</option>\n";
    }
  }
  $tmp .= "</select>";
}

sub message_rename()
{
  my ($context, $mbox, $oldfolder, $old, $newfolder, $new) = @_;
  my ($oldfile, $newfile);
  return if ($old eq $new) && ($oldfolder eq $newfolder);

  if ($context =~ /^(\w+)$/) {
    $context = $1;
  } else {
    die("Invalid Context<BR>\n");
  }

  if ($mbox =~ /^(\w+)$/) {
    $mbox = $1;
  } else {
    die ("Invalid mailbox<BR>\n");
  }

  if ($oldfolder =~ /^(\w+)$/) {
    $oldfolder = $1;
  } else {
    die("Invalid old folder<BR>\n");
  }

  if ($newfolder =~ /^(\w+)$/) {
    $newfolder = $1;
  } else {
    die("Invalid new folder ($newfolder)<BR>\n");
  }

  if ($old =~ /^(\d\d\d\d)$/) {
    $old = $1;
  } else {
    die("Invalid old Message<BR>\n");
  }

  if ($new =~ /^(\d\d\d\d)$/) {
    $new = $1;
  } else {
    die("Invalid old Message<BR>\n");
  }

  my $path = "/var/spool/asterisk/voicemail/$context/$mbox/$newfolder";
  $path =~ /^(.*)$/;
  $path = $1;
  mkdir $path, 0770;
  $path = "/var/spool/asterisk/voicemail/$context/$mbox/$oldfolder";
  opendir(DIR, $path) || die("Unable to open directory\n");
  my @files = grep /^msg${old}\.\w+$/, readdir(DIR);
  closedir(DIR);
  foreach $oldfile (@files) {
    my $tmp = $oldfile;
    if ($tmp =~ /^(msg${old}.\w+)$/) {
      $tmp = $1;
      $oldfile = $path . "/$tmp";
      $tmp =~ s/msg${old}/msg${new}/;
      $newfile = "/var/spool/asterisk/voicemail/$context/$mbox/$newfolder/$tmp";
#			print "Renaming $oldfile to $newfile<BR>\n";
      rename($oldfile, $newfile);
    }
  }
}

sub file_copy()
{
  my ($orig, $new) = @_;
  my $res;
  my $data;
  $orig =~ /^(.*)$/;
  $orig = $1;
  $new =~ /^(.*)$/;
  $new = $1;
  open(IN, "<$orig") || die("Unable to open '$orig'\n");
  open(OUT, ">$new") || DIE("Unable to open '$new'\n");
  while(($res = sysread(IN, $data, 4096)) > 0) {
    syswrite(OUT, $data, $res);
  }
  close(OUT);
  close(IN);
}

sub message_copy()
{
  my ($context, $mbox, $newmbox, $oldfolder, $old, $new) = @_;
  my ($oldfile, $newfile);
  return if ($mbox eq $newmbox);

  if ($mbox =~ /^(\w+)$/) {
    $mbox = $1;
  } else {
    die ("Invalid mailbox<BR>\n");
  }

  if ($newmbox =~ /^(\w+)$/) {
    $newmbox = $1;
  } else {
    die ("Invalid new mailbox<BR>\n");
  }

  if ($oldfolder =~ /^(\w+)$/) {
    $oldfolder = $1;
  } else {
    die("Invalid old folder<BR>\n");
  }

  if ($old =~ /^(\d\d\d\d)$/) {
    $old = $1;
  } else {
    die("Invalid old Message<BR>\n");
  }

  if ($new =~ /^(\d\d\d\d)$/) {
    $new = $1;
  } else {
    die("Invalid old Message<BR>\n");
  }

  my $path = "/var/spool/asterisk/voicemail/$context/$newmbox";
  $path =~ /^(.*)$/;
  $path = $1;
  mkdir $path, 0770;
  $path = "/var/spool/asterisk/voicemail/$context/$newmbox/INBOX";
  $path =~ /^(.*)$/;
  $path = $1;
  mkdir $path, 0770;
  $path = "/var/spool/asterisk/voicemail/$context/$mbox/$oldfolder";
  opendir(DIR, $path) || die("Unable to open directory\n");
  my @files = grep /^msg${old}\.\w+$/, readdir(DIR);
  closedir(DIR);
  foreach $oldfile (@files) {
    my $tmp = $oldfile;
    if ($tmp =~ /^(msg${old}.\w+)$/) {
      $tmp = $1;
      $oldfile = $path . "/$tmp";
      $tmp =~ s/msg${old}/msg${new}/;
      $newfile = "/var/spool/asterisk/voicemail/$context/$newmbox/INBOX/$tmp";
#			print "Copying $oldfile to $newfile<BR>\n";
      &file_copy($oldfile, $newfile);
    }
  }
}

sub message_delete()
{
  my ($context, $mbox, $folder, $msg) = @_;
  if ($mbox =~ /^(\w+)$/) {
    $mbox = $1;
  } else {
    die ("Invalid mailbox<BR>\n");
  }
  if ($context =~ /^(\w+)$/) {
    $context = $1;
  } else {
    die ("Invalid context<BR>\n");
  }
  if ($folder =~ /^(\w+)$/) {
    $folder = $1;
  } else {
    die("Invalid folder<BR>\n");
  }
  if ($msg =~ /^(\d\d\d\d)$/) {
    $msg = $1;
  } else {
    die("Invalid Message<BR>\n");
  }
  my $path = "/var/spool/asterisk/voicemail/$context/$mbox/$folder";
  opendir(DIR, $path) || die("Unable to open directory\n");
  my @files = grep /^msg${msg}\.\w+$/, readdir(DIR);
  closedir(DIR);
  foreach $oldfile (@files) {
    if ($oldfile =~ /^(msg${msg}.\w+)$/) {
      $oldfile = $path . "/$1";
#      print "Deleting $oldfile<BR>\n";
      unlink($oldfile);
    }
  }
}

sub message_forward()
{
  my ($toindex, @msgs) = @_;
  my $folder = param('folder');
  my ($mbox, $context) = split(/\@/, param('mailbox'));
  my $newmbox = param('forwardto');
  my $msg;
  my $msgcount;
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }
  $newmbox =~ s/(\w+)(\s+.*)?$/$1/;
  if (!&validmailbox($context, $newmbox)) {
    die("Bah! Not a valid mailbox '$newmbox'\n");
    return "";
  }

  my $txt;
  $context = &untaint($context);
  $newmbox = &untaint($newmbox);
  my $path = "/var/spool/asterisk/voicemail/$context/$newmbox/INBOX";
  if ($msgs[0]) {
    if (&lock_path($path) == 0) {
      $msgcount = &msgcount($context, $newmbox, "INBOX");

      if ($newmbox ne $mbox) {
        #			print header;
        foreach $msg (@msgs) {
          #				print "Forwarding $msg from $mbox to $newmbox<BR>\n";
          &message_copy($context, $mbox, $newmbox, $folder, $msg, sprintf "%04d", $msgcount);
          $msgcount++;
        }
        $txt = "<div class='alert alert-sm alert-success'>Forwarded messages " . join(', ', @msgs) . " to $newmbox</div>";
      } else {
        $txt = "<div class='alert alert-sm alert-danger'>Can't forward messages to yourself!\n</div>";
      }
      &unlock_path($path); 
    } else {
      $txt = "<div class='alert alert-sm alert-danger'>Cannot forward messages: Unable to lock path.\n</div>";
    }
  } else {
    $txt = "<div class='alert alert-sm alert-warning'>Please Select Message(s) for this action.\n</div>";
  }
  if ($toindex) {
    &message_index($folder, $txt);
  } else {
    &message_play($txt, $msgs[0]);
  }
}

sub message_delete_or_move()
{
  my ($toindex, $del, @msgs) = @_;
  my $txt;
  my $path;
  my ($y, $x);
  my $folder = param('folder');
  my $newfolder = param('newfolder') unless $del;
  $newfolder =~ s/^(\w+)\s+.*$/$1/;
  my ($mbox, $context) = split(/\@/, param('mailbox'));
  if (!$context) {
    $context = param('context');
  }
  if (!$context) {
    $context = "default";
  }
  my $passwd = param('password');
  $context = &untaint($context);
  $mbox = &untaint($mbox);
  $folder = &untaint($folder);
  $path = "/var/spool/asterisk/voicemail/$context/$mbox/$folder";
  if ($msgs[0]) {
    if (&lock_path($path) == 0) {
      my $msgcount = &msgcount($context, $mbox, $folder);
      my $omsgcount = &msgcount($context, $mbox, $newfolder) if $newfolder;
      #	print header;
      if ($newfolder ne $folder) {
        $y = 0;
        for ($x=0;$x<$msgcount;$x++) {
          my $msg = sprintf "%04d", $x;
          my $newmsg = sprintf "%04d", $y;
          if (grep(/^$msg$/, @msgs)) {
            if ($newfolder) {
              &message_rename($context, $mbox, $folder, $msg, $newfolder, sprintf "%04d", $omsgcount);
              $omsgcount++;
            } else {
              &message_delete($context, $mbox, $folder, $msg);
            }
          } else {
            &message_rename($context, $mbox, $folder, $msg, $folder, $newmsg);
            $y++;
          }
        }
        if ($del) {
          $txt = "<div class='alert alert-sm alert-success'>Deleted messages "  . join (', ', @msgs) . "</div>";
        } else {
          $txt = "<div class='alert alert-sm alert-success'>Moved messages "  . join (', ', @msgs) . " to $newfolder</div>";
        }
      } else {
        $txt = "<div class='alert alert-sm alert-danger'>Can't move a message to the same folder they're in already</div>";
      }
      &unlock_path($path);
    } else {
      $txt = "<div class='alert alert-sm alert-danger'>Cannot move/delete messages: Unable to lock path.</div>";
    }
  } else {
    $txt = "<div class='alert alert-sm alert-warning'>Please Select Message(s) for this action.\n</div>";
  }
  # Not as many messages now
  $msgcount--;
  if ($toindex || ($msgs[0] >= $msgcount)) {
    &message_index($folder, $txt);	
  } else {
    &message_play($txt, $msgs[0]);
  }
}

if (param()) {
  my $folder = param('folder');
  my $changefolder = param('changefolder');
  $changefolder =~ s/(\w+)\s+.*$/$1/;

  my $newfolder = param('newfolder');
  $newfolder =~ s/^(\w+)\s+.*$/$1/;
  if ($newfolder && !&validfolder($newfolder)) {
    print header;
    die("Bah! new folder '$newfolder' isn't a folder.");
  }
  $action = param('action');
  $msgid = param('msgid');
  if (!$action) {
    my ($tmp) = grep /^play\d\d\d\d\.x$/, param;
    if ($tmp =~ /^play(\d\d\d\d)/) {
      $msgid = $1;
      $action = "play";
    } else {
      print header;
      print "No message?<BR>\n";
      return;
    }
  }
  @msgs = param('msgselect');
  @msgs = ($msgid) unless @msgs;
  {
    ($mailbox) = &check_login();
    if (length($mailbox)) {
      if ($action eq 'login') {
        &message_index($folder, "Welcome, $mailbox");
      } elsif (($action eq 'refresh') || ($action eq 'index')) {
        &message_index($folder, "Welcome, $mailbox");
      } elsif ($action eq 'change to ->') {
        if (&validfolder($changefolder)) {
          $folder = $changefolder;
          &message_index($folder, "Welcome, $mailbox");
        } else {
          die("Bah!  Not a valid change to folder '$changefolder'\n");
        }
      } elsif ($action eq 'play') {
        &message_play("$mailbox $folder $msgid", $msgid);
      } elsif ($action eq 'preferences') {
        &message_prefs("refresh", $msgid);
      } elsif ($action eq 'download') {
        &message_audio(1);
      } elsif ($action eq 'play ') {
        &message_audio(0);
      } elsif ($action eq 'audio') {
        &message_audio(0);
      } elsif ($action eq 'delete') {
        &message_delete_or_move(1, 1, @msgs);
      } elsif ($action eq 'delete ') {
        &message_delete_or_move(0, 1, @msgs);
      } elsif ($action eq 'forward to ->') {
        &message_forward(1, @msgs);
      } elsif ($action eq 'forward to -> ') {
        &message_forward(0, @msgs);
      } elsif ($action eq 'save to ->') {
        &message_delete_or_move(1, 0, @msgs);
      } elsif ($action eq 'save to -> ') {
        &message_delete_or_move(0, 0, @msgs);
      } elsif ($action eq 'logout') {
        &login_screen("<div class='alert alert-sm alert-danger'>Logged out!</div>");
      }
    } else {
      sleep(1);
      &login_screen("<div class='alert alert-sm alert-danger'>Login Incorrect!</div>");
    }
  }
} else {
  &login_screen(" ");
}
