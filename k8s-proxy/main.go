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
	"sync"
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

	// Bidirectional copy
	var wg sync.WaitGroup
	var bytesIn, bytesOut int64

	wg.Add(2)

	// Client -> Target
	go func() {
		defer wg.Done()
		n, _ := copyBuffer(targetConn, clientConn)
		bytesIn = n
		targetConn.(*net.TCPConn).CloseWrite()
	}()

	// Target -> Client
	go func() {
		defer wg.Done()
		n, _ := copyBuffer(clientConn, targetConn)
		bytesOut = n
		clientConn.(*net.TCPConn).CloseWrite()
	}()

	wg.Wait()

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
