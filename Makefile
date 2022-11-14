systemdunitsdir := $(shell pkg-config --define-variable=prefix=$(prefix) --variable=systemdsystemunitdir systemd 2>/dev/null \
                     || echo $(libdir)/systemd/system/)
udevdir := $(shell pkg-config --define-variable=prefix=$(prefix) --variable=udevdir udev 2>/dev/null \
                     || echo $(libdir)/udev/)

install:
	install -D -m755 ds-inhibit.py "$(DESTDIR)/usr/bin/ds-inhibit"
	install -D -m644 systemd.service "$(DESTDIR)$(systemdunitsdir)/ds-inhibit.service"
