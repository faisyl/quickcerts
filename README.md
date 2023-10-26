# quickcerts

[![quickcerts](https://snapcraft.io//quickcerts/badge.svg)](https://snapcraft.io/quickcerts)

Quick and easy X.509 certificate generator for SSL/TLS utilizing local PKI

---

:heart: :heart: :heart:

You can say thanks to the author by donations to these wallets:

- ETH: `0xB71250010e8beC90C5f9ddF408251eBA9dD7320e`
- BTC:
  - Legacy: `1N89PRvG1CSsUk9sxKwBwudN6TjTPQ1N8a`
  - Segwit: `bc1qc0hcyxc000qf0ketv4r44ld7dlgmmu73rtlntw`

---

## Features

* Easy to use.
* Genarates both client and server certificates.
* Produces certificates with proper attributes (Key Usage, Extended Key Usage, Authority Key Identifier, Subject Key Identifier and so on).
* Supports certificates with multiple domain names (SAN, SubjectAlternativeName).
* Supports wildcard certificates.
* Generates PKCS12 (.pfx, .p12) as well

## Requirements

* Python 3.4+
* cryptography 1.6+

## Installation

#### From source

Run this command within source directory:

```sh
pip3 install .
```

#### From PyPI

```sh
pip3 install quickcerts
```

#### Snap Store

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/quickcerts)

```sh
sudo snap install quickcerts
```

#### Docker

For deployment with Docker see "Docker" section below.

## Usage example

```bash
quickcerts -D *.example.com example.com -D www.example2.com example2.com mx.example2.com -C "John Doe" -C "Jane Doe"
```

```bash
quickcerts -D localhost 127.0.0.1
```

These commands will produce following files in current directory:
* CA certificate and key
* Two server certificates having multiple DNS names or IP addresses in SubjectAlternativeName fields and keys for that certificates.
* Two client certificates for CN="John Doe" and CN="Jane Doe" (and keys for them).

Consequent invokations will reuse created CA.

## Docker

Also you may run this application with Docker:

```sh
docker run -it --rm -v "$(pwd)/certs:/certs" \
    yarmak/quickcerts -D server -C client1 -C client2 -C client3
```

In this example CA and certificates will be created in `./certs` directory.

## Synopsis

```
$ quickcerts --help
usage: quickcerts [-h] [-o OUTPUT_DIR] [-k KEY_SIZE] [--kdf-rounds KDF_ROUNDS]
                  [-D DOMAINS [DOMAINS ...]] [-C CLIENT] [-P PASSWORD]

Generate RSA certificates signed by common self-signed CA

options:
  -h, --help            show this help message and exit
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        location of certificates output (default: .)
  -k KEY_SIZE, --key-size KEY_SIZE
                        RSA key size used for all certificates (default: 2048)
  --kdf-rounds KDF_ROUNDS
                        number of KDF rounds (default: 50000)
  -D DOMAINS [DOMAINS ...], --domains DOMAINS [DOMAINS ...]
                        Generate server certificate which covers following
                        domains or IP addresses delimited by spaces. First one
                        will be set as CN. Option can be used multiple times.
                        (default: None)
  -C CLIENT, --client CLIENT
                        Generate client certificate with following name.
                        (default: None)
  -P PASSWORD, --password PASSWORD
                        password for newly generated .pfx files (default:
                        password)
  -S, --server          Serve certificates over TCP. (default: False)
  -p PORT, --port PORT  Port to serve on, if serving on TCP (default: 8080)
```

## Run As Server
Run the CA as a network service to allow you to dynamically generate and fetch 
certificates over the network with a simple curl or wget command. 
Running quickcerts with -S enables the web server on port 8080, which can be overridden 
with the -p argument.

This is nice to have in a development environment where you want to quickly fetch the TLS 
certificates for both client and server mode services with a simple command line or automated fetch 
as part of service startup.

### Fetch CA cert

```$ curl -JLO http://<SERVER-IP/HOSTNAME>:8080/ca ```
OR 
```$ wget --content-disposition http://<SERVER-IP/HOSTNAME>:8080/ca ```

This should download and place in your current directory a file named ca-cert.zip. This is simply a 
zipfile containing the CA's public certificate in PEM format.

You could alternatively use the --output <filename.zip> for curl and -O <filename.zip> for wget to save the
URL to filename.zip.

### Fetch Client Cerificate pair

The URL for the client cert:

``` http://<SERVER-IP/HOSTNAME>:8080/client/<client-name>[/force]```

This will fetch a zipfile containing the newly created client cert for the given <client-name> or fetch 
an existing key-pair if available.  Adding the optional ```/force``` to the end of the URL forces the server 
to delete any existing keypair of the same name and generate a new pair with the given name.
The zipfile also contains the ```ca.pem``` for ease of use.

### Fetch Server certificate pair

The URL for the server cert:

``` http://<SERVER-IP/HOSTNAME>:8080/server/<server-name>[,<san1>,<san2>..][/force]```

This will fetch a zipfile containing the newly created server cert pair. The filenames in the cert are the IP 
address of the client. The cert pair contains the <server-name>, IP and optional SAN names including wildcard 
addresses passed in the URL. Please make sure you quote the URL appropriately when using wget or curl on the 
command line with wildcard addresses like ```*.foo.com```, to prevent the shell from trying to expand the URL 
before passing it to curl or wget.

As with the client above, ending the URL with ```/force``` will cause the CA to delete existing keypairs of the same
name (IP address) and generate a new pair. This is useful if you need to update or change the embedded hostmname 
or SAN entries in the certificate.

### Running under docker compose
Also included is a docker-compose.yaml file that you can use with docker compose to run the server. Simply running
```$ docker compose up -d``` should bring up the server on your machine on port 8080. It will map the certs directory 
to /certs and store the certificates there.

***NOTE:*** The service runs in host-mode networking to allow it to see the correct IP of the client when generating
server certificates. Without that, docker would present the NATed docker network IP for the client IP and the server
certificates would not work properly.


 