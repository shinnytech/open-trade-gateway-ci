# open-trade-gateway-ci

The Kylin ARM workflow builds one ARM64 gateway package. Production and
evaluation modes share the same XC Trader API and are selected at runtime with
the upstream `is_production_mode` configuration.
