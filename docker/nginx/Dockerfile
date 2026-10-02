FROM nginx:1.28-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY templates /etc/nginx/global-exchange-templates
COPY entrypoint.sh /usr/local/bin/global-exchange-nginx

RUN sed -i 's/\r$//' /usr/local/bin/global-exchange-nginx \
    && chmod +x /usr/local/bin/global-exchange-nginx

EXPOSE 8080 8081 8443
ENTRYPOINT ["/usr/local/bin/global-exchange-nginx"]
