#!/usr/bin/env python3

import argparse
import datetime
import ipaddress
import uuid
import os.path
import re
import socket
import string
import web
import zipstream

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

DAY = datetime.timedelta(1, 0, 0)
CA_FILENAME = 'ca'
KEY_EXT = 'key'
CERT_EXT = 'pem'
PFX_EXT = 'pfx'
E = 65537
ca_private_key = None
ca_cert = None
args = None

safe_symbols = set(string.ascii_letters + string.digits + '-.')

def safe_filename(name):
    return "".join(c if c in safe_symbols else '_' for c in name)

def is_ipaddress(name):
    try:
        socket.getaddrinfo(name, 0, flags=socket.AI_NUMERICHOST)
        return True
    except socket.gaierror:
        return False

def parse_args():
    def check_keysize(val):
        def fail():
            raise argparse.ArgumentTypeError("%s is not valid key size" % (repr(val),))
        try:
            ival = int(val)
        except ValueError:
            fail()
        if not 1024 <= ival <= 8192:
            fail()
        return ival

    def check_uint(val):
        def fail():
            raise argparse.ArgumentTypeError("%s is not valud unsigned int" % (repr(val),))
        try:
            ival = int(val)
        except ValueError:
            fail()
        if ival < 0:
            fail()
        return ival

    parser = argparse.ArgumentParser(
        description="Generate RSA certificates signed by common self-signed CA",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-o", "--output-dir",
                        default='.',
                        help="location of certificates output")
    parser.add_argument("-k", "--key-size",
                        type=check_keysize,
                        default=2048,
                        help="RSA key size used for all certificates")
    parser.add_argument("--kdf-rounds",
                        type=check_uint,
                        default=50000,
                        help="number of KDF rounds")
    parser.add_argument("-D", "--domains",
                        action="append",
                        nargs="+",
                        help="Generate server certificate which covers "
                        "following domains or IP addresses delimited by spaces. "
                        "First one will be set as CN. "
                        "Option can be used multiple times.")
    parser.add_argument("-C", "--client",
                        action="append",
                        help="Generate client certificate with following name.")
    parser.add_argument("-P", "--password",
                        default='password',
                        help="password for newly generated .pfx files")
    parser.add_argument("-S", "--server", default=False, action='store_true',
                        help="Serve certificates over TCP.")
    parser.add_argument("-p", "--port", default=8080, type=int,
                        help="Port to serve on, if serving on TCP")

    return parser.parse_args()

def ensure_private_key(output_dir, name, key_size):
    key_filename = os.path.join(output_dir, safe_filename(name) + '.' + KEY_EXT)
    if os.path.exists(key_filename):
        with open(key_filename, "rb") as key_file:
            private_key = serialization.load_pem_private_key(key_file.read(),
                password=None, backend=default_backend())
    else:
        private_key = rsa.generate_private_key(public_exponent=E,
            key_size=key_size, backend=default_backend())
        with open(key_filename, 'wb') as key_file:
            key_file.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()))
    return private_key

def ensure_ca_key(output_dir, key_size):
    return ensure_private_key(output_dir, CA_FILENAME, key_size)

ca_cert_filename = None

def ensure_ca_cert(output_dir, ca_private_key):
    global ca_cert_filename
    ca_cert_filename = os.path.join(output_dir, CA_FILENAME + '.' + CERT_EXT)
    ca_public_key = ca_private_key.public_key()
    if os.path.exists(ca_cert_filename):
        with open(ca_cert_filename, "rb") as ca_cert_file:
            ca_cert = x509.load_pem_x509_certificate(
                ca_cert_file.read(),
                backend=default_backend())
    else:
        iname = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'QuickCert CA'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                'QuickCert'),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME,
                'QuickCert tool'),
        ])
        ca_cert = x509.CertificateBuilder().\
            subject_name(iname).\
            issuer_name(iname).\
            not_valid_before(datetime.datetime.today() - DAY).\
            not_valid_after(datetime.datetime.today() + 3650 * DAY).\
            serial_number(x509.random_serial_number()).\
            public_key(ca_public_key).\
            add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True).\
            add_extension(
                x509.KeyUsage(digital_signature=False,
                              content_commitment=False,
                              key_encipherment=False,
                              data_encipherment=False,
                              key_agreement=False,
                              key_cert_sign=True,
                              crl_sign=True,
                              encipher_only=False,
                              decipher_only=False),
                critical=True).\
            add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_public_key),
                critical=False).\
            sign(
                private_key=ca_private_key,
                algorithm=hashes.SHA256(),
                backend=default_backend()
            )
        with open(ca_cert_filename, "wb") as ca_cert_file:
            ca_cert_file.write(
                ca_cert.public_bytes(encoding=serialization.Encoding.PEM))
    assert isinstance(ca_cert, x509.Certificate)
    return ca_cert

def ensure_end_entity_key(output_dir, name, key_size):
    return ensure_private_key(output_dir, name, key_size)

def ensure_end_entity_cert(output_dir, names, ca_private_key, ca_cert, end_entity_public_key, is_server=True):
    name = names[0]
    end_entity_cert_filename = os.path.join(output_dir, safe_filename(name) + '.' + CERT_EXT)
    if os.path.exists(end_entity_cert_filename):
        with open(end_entity_cert_filename, "rb") as end_entity_cert_file:
            end_entity_cert = x509.load_pem_x509_certificate(
                end_entity_cert_file.read(),
                backend=default_backend())
            return end_entity_cert
    ca_public_key = ca_private_key.public_key()
    end_entity_cert_builder = x509.CertificateBuilder().\
        subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name),
        ])).\
        issuer_name(ca_cert.subject).\
        not_valid_before(datetime.datetime.today() - DAY).\
        not_valid_after(datetime.datetime.today() + 3650 * DAY).\
        serial_number(x509.random_serial_number()).\
        public_key(end_entity_public_key).\
        add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True).\
        add_extension(
            x509.KeyUsage(digital_signature=True,
                          content_commitment=False,
                          key_encipherment=True,
                          data_encipherment=False,
                          key_agreement=False,
                          key_cert_sign=False,
                          crl_sign=False,
                          encipher_only=False,
                          decipher_only=False),
            critical=True).\
        add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH if is_server else ExtendedKeyUsageOID.CLIENT_AUTH,
            ]), critical=False).\
        add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_public_key),
            critical=False).\
        add_extension(
            x509.SubjectKeyIdentifier.from_public_key(end_entity_public_key),
            critical=False)
    if is_server:
        end_entity_cert_builder = end_entity_cert_builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(n)) if is_ipaddress(n) else x509.DNSName(n) for n in names]
            ),
            critical=False
        )
    end_entity_cert = end_entity_cert_builder.\
        sign(
            private_key=ca_private_key,
            algorithm=hashes.SHA256(),
            backend=default_backend()
        )
    with open(end_entity_cert_filename, "wb") as end_entity_cert_file:
        end_entity_cert_file.write(
            end_entity_cert.public_bytes(encoding=serialization.Encoding.PEM))
    return end_entity_cert

def ensure_end_entity_pfx(output_dir, name, end_entity_key, end_entity_cert, kdf_rounds=50000, password=b"password"):
    end_entity_pfx_filename = os.path.join(output_dir, safe_filename(name) + '.' + PFX_EXT)
    encryption = serialization.PrivateFormat.PKCS12.encryption_builder().\
        kdf_rounds(kdf_rounds).\
        key_cert_algorithm(serialization.pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC).\
        hmac_hash(hashes.SHA1()).\
        build(password)
    end_entity_pfx = serialization.pkcs12.serialize_key_and_certificates(
        name.encode("utf-8"),
        end_entity_key,
        end_entity_cert,
        None,
        encryption)
    with open(end_entity_pfx_filename, "wb") as end_entity_pfx_file:
        end_entity_pfx_file.write(end_entity_pfx)

def ensure_end_entity_suite(output_dir, names, ca_private_key, ca_cert, key_size,
                            is_server=True, kdf_rounds=50000, password=b"password"):
    name = names[0]
    end_entity_key = ensure_end_entity_key(output_dir, name, key_size)
    end_entity_public_key = end_entity_key.public_key()
    end_entity_cert = ensure_end_entity_cert(output_dir,
                           names,
                           ca_private_key,
                           ca_cert,
                           end_entity_public_key,
                           is_server)
    if not is_server:
        ensure_end_entity_pfx(output_dir, name, end_entity_key, end_entity_cert, kdf_rounds, password.encode("utf-8"))

def zf(zipname, files):
        web.header('Content-type' , 'application/zip')
        web.header('Content-Disposition', 'attachment; filename="%s"' % (
        zipname,))
        web.header('Transfer-Encoding','chunked')
        ret = zipstream.ZipFile()
        for f in files:
            ret.write(f)
        return ret.__iter__()

def delcerts(prefix):
    global args
    for fn in filelist(prefix):
        if os.path.exists(fn):
            print("Deleting:", fn)
            os.unlink(fn)
class ca:
    def GET(self):
        global ca_cert_filename
        zip_filename = 'ca.zip'
        return zf('ca-cert.zip', [ca_cert_filename])

def filelist(prefix, exists=False, with_ca=False):
    global args
    ret = []
    if with_ca:
        ret.append(os.path.join(args.output_dir, "ca.pem"))
    for ext in [CERT_EXT, KEY_EXT, PFX_EXT]:
        fn = os.path.join(args.output_dir, "{}.{}".format(prefix, ext))
        if exists:
            if os.path.exists(fn):
                ret.append(fn)
        else:
            ret.append(fn)
    return ret

class client:
    def GET(self, _args):
        global ca_cert, ca_private_key, args
        all = [x.strip() for x in _args.split('/')]
        names = [x.strip() for x in all[0].split(',')]
        CN=names[0]
        if CN=='ca':
            raise web.Forbidden('Reserved for CA')
        force = (all[-1] == 'force')
        if force:
            delcerts(CN)
        ensure_end_entity_suite(args.output_dir,
                                (CN,),
                                ca_private_key,
                                ca_cert,
                                args.key_size,
                                False,
                                args.kdf_rounds,
                                args.password)
        flist = filelist(CN, exists=True, with_ca=True) 
        return zf(f"{CN}.zip", flist)


class server:
    def GET(self, _args):
        global args
        all = [x.strip() for x in _args.split('/')]
        ip = web.ctx.ip
        names =[ip] + [x.strip() for x in all[0].split(',')]
        force = (all[-1] == 'force')
        if force:
            delcerts(ip)
        ensure_end_entity_suite(args.output_dir,
                                names,
                                ca_private_key,
                                ca_cert,
                                args.key_size,
                                True,
                                args.kdf_rounds,
                                args.password)
        flist = filelist(ip, exists=True, with_ca=True) 
        return zf(f"{ip}.zip", flist)

urls = (
    '/ca', 'ca',
    '/client/(.+)', 'client',           # /client/client-name[/force]
    '/server/(.+)', 'server',           # /server/SAN1,SAN2,SAN3[/force]
)


def main():
    global args
    global ca_private_key, ca_cert
    args = parse_args()
    ca_private_key = ensure_ca_key(args.output_dir, args.key_size)
    ca_cert = ensure_ca_cert(args.output_dir, ca_private_key)
    if args.server:
        app = web.application(urls, globals())
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", args.port))
    if args.domains:
        for names in args.domains:
            ensure_end_entity_suite(args.output_dir,
                                    names,
                                    ca_private_key,
                                    ca_cert,
                                    args.key_size,
                                    True,
                                    args.kdf_rounds,
                                    args.password)
    if args.client:
        for name in args.client:
            ensure_end_entity_suite(args.output_dir,
                                    (name,),
                                    ca_private_key,
                                    ca_cert,
                                    args.key_size,
                                    False,
                                    args.kdf_rounds,
                                    args.password)

if __name__ == '__main__':
    main()
