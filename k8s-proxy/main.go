// GLaDOS TCP Proxy
// A minimal TCP proxy that forwards connections to a GPU server running GLaDOS.
// Designed to run in K8s to bridge NEWT tunnel to an external GPU server.
//
// Usage: glados-proxy -target GPU_SERVER_IP:5555 -listen :5555
//
package main

import (
	"flag"
	"io"
	"log"
	"net"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"
)

var (
	listenAddr  = flag.String("listen", ":5555", "Address to listen on")
	targetAddr  = flag.String("target", "", "Target GPU server address (e.g., 192.168.1.100:5555)")
	dialTimeout = flag.Duration("timeout", 10*time.Second, "Connection timeout to target")
	bufferSize  = flag.Int("buffer", 32*1024, "Buffer size for copying data")
)

var (
	activeConns   int64
	totalConns    int64
	totalBytes    int64
)

func main() {
	flag.Parse()

	// Check for environment variable override
	if envTarget := os.Getenv("GLADOS_TARGET"); envTarget != "" {
		*targetAddr = envTarget
	}

	if *targetAddr == "" {
		log.Fatal("Error: -target or GLADOS_TARGET environment variable is required")
	}

	log.Printf("GLaDOS TCP Proxy starting...")
	log.Printf("  Listen: %s", *listenAddr)
	log.Printf("  Target: %s", *targetAddr)

	listener, err := net.Listen("tcp", *listenAddr)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", *listenAddr, err)
	}
	defer listener.Close()

	log.Printf("Proxy ready, forwarding connections to %s", *targetAddr)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		log.Printf("Shutting down... (active connections: %d)", atomic.LoadInt64(&activeConns))
		listener.Close()
	}()

	// Stats logger
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		for range ticker.C {
			log.Printf("Stats: active=%d total=%d bytes=%d",
				atomic.LoadInt64(&activeConns),
				atomic.LoadInt64(&totalConns),
				atomic.LoadInt64(&totalBytes))
		}
	}()

	// Accept connections
	for {
		clientConn, err := listener.Accept()
		if err != nil {
			if opErr, ok := err.(*net.OpError); ok && opErr.Err.Error() == "use of closed network connection" {
				break // Graceful shutdown
			}
			log.Printf("Accept error: %v", err)
			continue
		}

		go handleConnection(clientConn)
	}

	log.Printf("Proxy stopped")
}

func handleConnection(clientConn net.Conn) {
	connID := atomic.AddInt64(&totalConns, 1)
	atomic.AddInt64(&activeConns, 1)
	defer atomic.AddInt64(&activeConns, -1)

	clientAddr := clientConn.RemoteAddr().String()
	log.Printf("[%d] New connection from %s", connID, clientAddr)

	// Connect to target GPU server
	targetConn, err := net.DialTimeout("tcp", *targetAddr, *dialTimeout)
	if err != nil {
		log.Printf("[%d] Failed to connect to target %s: %v", connID, *targetAddr, err)
		clientConn.Close()
		return
	}

	log.Printf("[%d] Connected to target %s", connID, *targetAddr)

	// Disable Nagle's algorithm for lower latency
	if tc, ok := clientConn.(*net.TCPConn); ok {
		tc.SetNoDelay(true)
		tc.SetKeepAlive(true)
		tc.SetKeepAlivePeriod(30 * time.Second)
	}
	if tc, ok := targetConn.(*net.TCPConn); ok {
		tc.SetNoDelay(true)
		tc.SetKeepAlive(true)
		tc.SetKeepAlivePeriod(30 * time.Second)
	}

	// Use a done channel to coordinate shutdown
	done := make(chan struct{})
	var bytesIn, bytesOut int64

	// Client -> Target
	go func() {
		n, err := copyBuffer(targetConn, clientConn)
		bytesIn = n
		if err != nil {
			log.Printf("[%d] Client->Target error: %v", connID, err)
		}
		// Signal the other direction to stop
		targetConn.(*net.TCPConn).CloseWrite()
		close(done)
	}()

	// Target -> Client (runs in main goroutine for this connection)
	n, err := copyBuffer(clientConn, targetConn)
	bytesOut = n
	if err != nil {
		log.Printf("[%d] Target->Client error: %v", connID, err)
	}
	clientConn.(*net.TCPConn).CloseWrite()

	// Wait for the other direction to finish
	<-done

	clientConn.Close()
	targetConn.Close()

	totalBytesTransferred := bytesIn + bytesOut
	atomic.AddInt64(&totalBytes, totalBytesTransferred)

	log.Printf("[%d] Connection closed (in=%d out=%d bytes)", connID, bytesIn, bytesOut)
}

func copyBuffer(dst io.Writer, src io.Reader) (int64, error) {
	buf := make([]byte, *bufferSize)
	return io.CopyBuffer(dst, src, buf)
}
