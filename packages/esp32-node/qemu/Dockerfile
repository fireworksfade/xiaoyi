# Builds the xiaoyi-node firmware releases with ESP-IDF and packages them with
# Espressif's QEMU so every container boots a real ESP32 firmware image.
ARG IDF_IMAGE=espressif/idf:v5.5.4
ARG RUNTIME_IMAGE=python:3.12-slim-bookworm

# QEMU's shared libraries and the flashing tools, independent of the firmware so
# this layer stays cached while firmware changes.
FROM ${RUNTIME_IMAGE} AS runtime-base
# Package mirrors, overridable where the official hosts are slow (see .env.example).
# APT always goes over HTTPS: some proxies break plain HTTP on port 80.
ARG DEBIAN_MIRROR=https://deb.debian.org
ARG PYPI_INDEX=https://pypi.org/simple
RUN sed -i "s#http://deb.debian.org#${DEBIAN_MIRROR}#g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libpixman-1-0 libslirp0 libsdl2-2.0-0 libgcrypt20 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --index-url "${PYPI_INDEX}" \
    "esptool==4.8.1" "esp-idf-nvs-partition-gen==0.1.9"

FROM ${IDF_IMAGE} AS firmware
# Releases served by the OTA server. FAULTY_VERSIONS never pass their boot
# self-test and exist to rehearse automatic rollback.
ARG FIRMWARE_VERSIONS="1.1.4 1.2.0 1.3.1 1.3.9 1.4.0"
ARG FAULTY_VERSIONS="1.4.1-rc1"
# Espressif's mirror of GitHub release assets (much faster where GitHub is slow).
ARG IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
ENV IDF_GITHUB_ASSETS=${IDF_GITHUB_ASSETS}
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /src
RUN python "$IDF_PATH/tools/idf_tools.py" install qemu-xtensa \
    && qemu="$(find /opt/esp/tools/qemu-xtensa -path '*/bin/qemu-system-xtensa' -type f | head -n 1)" \
    && mkdir -p /out \
    && cp -r "$(dirname "$(dirname "$qemu")")" /out/qemu
COPY CMakeLists.txt partitions.csv sdkconfig.defaults sdkconfig.defaults.qemu ./
COPY main ./main
RUN . "$IDF_PATH/export.sh" > /dev/null \
    && mkdir -p /out/firmware /out/base \
    && build() { \
        idf.py -B build -D SDKCONFIG=build/sdkconfig \
            -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.qemu" \
            -D "XIAOYI_FW_VERSION=$1" -D "XIAOYI_FAULTY_BUILD=$2" build > /tmp/build.log 2>&1 \
            || { tail -n 80 /tmp/build.log; return 1; }; \
        cp build/xiaoyi-node.bin "/out/firmware/xiaoyi-node-$1.bin"; \
        cp build/xiaoyi-node.elf "/out/firmware/xiaoyi-node-$1.elf"; \
        echo "built xiaoyi-node $1 (faulty=$2)"; \
    } \
    && for version in $FIRMWARE_VERSIONS; do build "$version" OFF; done \
    && for version in $FAULTY_VERSIONS; do build "$version" ON; done \
    && cp build/bootloader/bootloader.bin build/partition_table/partition-table.bin \
          build/ota_data_initial.bin /out/base/

FROM runtime-base
COPY --from=firmware /out/qemu /opt/qemu
COPY --from=firmware /out/firmware /opt/xiaoyi/firmware
COPY --from=firmware /out/base /opt/xiaoyi/base
COPY qemu/entrypoint.sh qemu/provision.py qemu/netfault.py /opt/xiaoyi/bin/
RUN sed -i 's/\r$//' /opt/xiaoyi/bin/* \
    && chmod +x /opt/xiaoyi/bin/* \
    && /opt/qemu/bin/qemu-system-xtensa --version
ENV PATH="/opt/xiaoyi/bin:/opt/qemu/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1
VOLUME ["/flash"]
ENTRYPOINT ["/opt/xiaoyi/bin/entrypoint.sh"]
