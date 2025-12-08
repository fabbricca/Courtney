# GLaDOS TCP Proxy - Minimal Docker image
# Multi-stage build for smallest possible image

FROM golang:1.21-alpine AS builder

WORKDIR /build

# Copy go module files
COPY go.mod ./

# Copy source
COPY main.go ./

# Build static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-w -s" -o glados-proxy .

# Final minimal image
FROM scratch

# Copy the binary
COPY --from=builder /build/glados-proxy /glados-proxy

# Expose the proxy port
EXPOSE 5555

# Run the proxy
ENTRYPOINT ["/glados-proxy"]
