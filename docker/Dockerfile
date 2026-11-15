FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

# On Apple Silicon or ARM64 systems, replace x86_64 with aarch64:
# aws-emulator-aarch64.rpm
ARG ARCH=x86_64
ADD https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator-${ARCH}.rpm /tmp/aws-emulator.rpm

RUN rpm -i /tmp/aws-emulator.rpm && rm /tmp/aws-emulator.rpm \
    && mkdir -p /home/emulator && chown 1000 /home/emulator

USER 1000
ENV HOME=/home/emulator
EXPOSE 9297

# Bind 0.0.0.0 inside the container so Docker can forward the port to 127.0.0.1 on the host
ENTRYPOINT ["aws-emulator", "-b", "0.0.0.0"]
