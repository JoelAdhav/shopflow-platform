# Single stage on purpose: plain HTML/JS has no build step, so there is nothing
# for a builder stage to do. If the frontend ever gets a bundler, add
# "FROM node:... AS build" above and COPY --from=build the output.
#
# nginx-unprivileged: official nginx variant that runs as UID 101 and listens
# on 8080 (ports below 1024 need root).
FROM nginxinc/nginx-unprivileged:1.31.7-alpine3.24
ENV API_UPSTREAM=api:8000
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY html /usr/share/nginx/html
EXPOSE 8080
