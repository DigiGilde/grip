# The bootstrap of one peer (deploy/zad/fsc/bootstrap.sh) as a component in
# the deployment of that peer: the internal APIs of its manager and controller
# are only reachable from there. Modelled on the contract bootstrap component
# in demo/environment/federatie/contracts of MinBZK/moza-poc-fbs-berichtenbox.
# ZAD runs only long-lived components and passes no command arguments, so the
# entrypoint itself says --loop.
# Build context: deploy/zad/fsc (its .dockerignore lets only bootstrap.sh in).
FROM docker.io/library/alpine:3.24.4@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

RUN apk add --no-cache curl jq
COPY --chmod=0555 bootstrap.sh /usr/local/bin/fsc-bootstrap
USER 1001
ENTRYPOINT ["/usr/local/bin/fsc-bootstrap", "--loop"]
