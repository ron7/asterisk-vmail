#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/types.h>

int main(void)
{

  int real = getuid();
  int euid = geteuid();

  setuid(geteuid());
  system("$(which perl) ./vmail.cgi");

  printf("<!-- UID: %d, eUID: %d -->", real,euid);
}
