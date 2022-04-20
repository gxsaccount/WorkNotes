token_t scan_token( FILE *fp ) {
int c = fgetc(fp);
if(c==’*’) {
return TOKEN_MULTIPLY;
} else if(c==’!’) {
char d = fgetc(fp);
if(d==’=’) {
return TOKEN_NOT_EQUAL;
} else {
ungetc(d,fp);
return TOKEN_NOT;
}
} else if(isalpha(c)) {
do {
char d = fgetc(fp);
} while(isalnum(d));
ungetc(d,fp);
return TOKEN_IDENTIFIER;
} else if ( . . . ) {
. . .
}
}