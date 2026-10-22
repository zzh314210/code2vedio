package main

import (
	"context"
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

func main() {
	root := flag.String("root", "/data/code2vedio", "project root")
	listen := flag.String("listen", "127.0.0.1:7860", "HTTP listen address")
	importPlatform := flag.String("import-platform", "", "import server-only model config from a local JSON file")
	initialize := flag.Bool("init-only", false, "initialize accounts and exit")
	upgradeReasoning := flag.Bool("upgrade-reasoning-defaults", false, "upgrade legacy platform thinking defaults, preserving keys and prices")
	outputLimit := flag.Int("raise-text-output-limit", 0, "raise enabled platform text model output limits, preserving all other settings")
	outputTask := flag.String("output-limit-task", "", "apply the output limit to one archived task instead of the platform catalog")
	reset := flag.String("reset-password", "", "reset one username using C2V_NEW_PASSWORD")
	preview := flag.Bool("preview", false, "isolate preview browser sessions")
	flag.Parse()
	syscall.Umask(0077)
	store, err := openStore(filepath.Join(*root, "private"))
	if err != nil {
		log.Fatal(err)
	}
	defer store.DB.Close()
	if err = store.bootstrap(); err != nil {
		log.Fatal(err)
	}
	if *upgradeReasoning {
		n, err := store.upgradeReasoningDefaults()
		if err != nil {
			log.Fatal(err)
		}
		log.Printf("Upgraded reasoning defaults for %d platform models; credentials and prices preserved", n)
		return
	}
	if *outputLimit != 0 {
		n, err := store.raiseTextOutputLimit(*outputLimit, *outputTask)
		if err != nil {
			log.Fatal(err)
		}
		log.Printf("Raised text output limit to %d for %d configurations; other settings preserved", *outputLimit, n)
		return
	}
	if *outputTask != "" {
		log.Fatal("output-limit-task requires raise-text-output-limit")
	}
	if *importPlatform != "" {
		if err = store.importPlatform(*importPlatform); err != nil {
			log.Fatal(err)
		}
		log.Print("Platform model configuration encrypted and imported")
		return
	}
	if *reset != "" {
		password := os.Getenv("C2V_NEW_PASSWORD")
		if err = store.resetPassword(*reset, password); err != nil {
			log.Fatal(err)
		}
		log.Print("Password reset; all sessions revoked")
		return
	}
	if *initialize {
		log.Print("Accounts initialized; administrator credentials stored in private/admin-access.txt")
		return
	}
	origins := strings.Split(os.Getenv("C2V_ALLOWED_ORIGINS"), ",")
	origins = append(origins, "http://127.0.0.1:7860", "http://localhost:7860", "http://127.0.0.1:5173", "http://localhost:5173")
	handler, err := newServer(store, filepath.Join(*root, "web/dist"), filepath.Join(*root, "private/worker.sock"), origins)
	if err != nil {
		log.Fatalf("Initialize API: %v", err)
	}
	if *preview {
		handler.CookieName = "frame_preview_session"
	}
	socket := filepath.Join(*root, "private/api.sock")
	os.Remove(socket)
	listener, err := net.Listen("unix", socket)
	if err != nil {
		log.Fatal(err)
	}
	defer listener.Close()
	defer os.Remove(socket)
	internal := &http.Server{Handler: handler, ReadHeaderTimeout: 10 * time.Second}
	go internal.Serve(listener)
	server := &http.Server{Addr: *listen, Handler: handler, ReadHeaderTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 64 * 1024}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-stop
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		server.Shutdown(ctx)
	}()
	log.Printf("Frame Go API listening on %s", *listen)
	if err = server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
