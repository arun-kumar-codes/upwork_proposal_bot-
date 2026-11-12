"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FlaskConical, FolderKanban, History, LogOut, Upload, Users } from "lucide-react";
import { ThemeToggle } from "./theme-toggle";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Button } from "./ui/button";

const LINKS = [
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/profiles", label: "Profiles", icon: Users },
  { href: "/import", label: "Import", icon: Upload },
  { href: "/playground", label: "Playground", icon: FlaskConical },
  { href: "/history", label: "History", icon: History },
];

export function Nav() {
  const pathname = usePathname();
  const { logout } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b bg-background">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link href="/projects" className="text-base font-bold tracking-tight">
          Project Hub
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                pathname === href
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="h-4 w-4" />
            Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
