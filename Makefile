.DEFAULT_GOAL := all

img4lib-install:
	@echo "building img4lib"
	$(MAKE) -C img4lib COMMONCRYPTO=1
	@echo "copying img4lib binary to /usr/local/bin"
	cp img4lib/img4 /usr/local/bin/img4

libfragmentzip-install:
	@echo "building libfragmentzip"
	cp libfragmentzip/include/libfragmentzip/libfragmentzip.h libfragmentzip/libfragmentzip/libfragmentzip.h # TEMPFIX
	cd libfragmentzip && ./autogen.sh
	$(MAKE) -C libfragmentzip 
	@echo "installing libfragmentzip"
	$(MAKE) -C libfragmentzip install

partialZipBrowser-install: 
	@echo "building partialZipBrowser"
	cd partialZipBrowser && touch NEWS AUTHORS ChangeLog && ./autogen.sh # TEMPFIX: `touch NEWS AUTHORS ChangeLog`
	$(MAKE) -C partialZipBrowser
	@echo "installing partialZipBrowser"
	$(MAKE) -C partialZipBrowser install

clean: 
	$(MAKE) -C img4lib clean
	$(MAKE) -C libfragmentzip clean
	$(MAKE) -C partialZipBrowser clean

all: img4lib-install libfragmentzip-install partialZipBrowser-install
	pip3 install -r requirements.txt --user