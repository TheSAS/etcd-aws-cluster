FROM gliderlabs/alpine:3.2

RUN apk --update add \
      python \
      py-pip \
      curl \
      bash &&\
    pip install --upgrade boto requests &&\
    mkdir /root/.aws

COPY etcd-aws-cluster.py /etcd-aws-cluster.py

# Expose volume for adding credentials
VOLUME ["/root/.aws"]

#Expose directory to write output to
VOLUME ["/etc/sysconfig/"]

CMD python /etcd-aws-cluster.py
