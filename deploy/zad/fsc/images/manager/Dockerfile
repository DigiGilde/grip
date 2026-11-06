# Modelled on deploy/zad/manager-migrate in MinBZK/moza-fsc-testnet.
# Thin layer over the stock OpenFSC manager image: migrate, then serve. ZAD has
# no init containers and no command arguments.
# The stock image is distroless (no /bin/sh), so a static busybox is added as
# /bin/sh; permissions come from COPY --chmod because RUN would need a shell.
ARG OPENFSC_VERSION=v2.8.0

FROM busybox:1.38.0-musl@sha256:ea2b9914a16a4ac1981994af97b318f7c7d4db76b580c56177f08bf76f4a0be8 AS busybox

FROM docker.io/federatedserviceconnectivity/manager:${OPENFSC_VERSION}
COPY --from=busybox /bin/busybox /bin/sh
COPY --chmod=0555 entrypoint.sh /usr/local/bin/migrate-and-serve.sh
ENTRYPOINT ["/usr/local/bin/migrate-and-serve.sh"]
