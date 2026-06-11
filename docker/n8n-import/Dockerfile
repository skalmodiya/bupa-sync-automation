FROM n8nio/n8n:latest

USER root

WORKDIR /workflows
COPY workflows/ /workflows/
COPY import.sh /import.sh
RUN sed -i 's/\r$//' /import.sh && chmod +x /import.sh

USER node
ENTRYPOINT ["/import.sh"]
