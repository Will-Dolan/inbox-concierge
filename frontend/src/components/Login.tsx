import { Inbox } from "lucide-react";
import { api } from "../api";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

export function Login() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-sm text-center shadow-sm">
        <CardHeader>
          <Inbox className="mx-auto mb-1 h-9 w-9 text-foreground" strokeWidth={1.5} />
          <h1 className="text-lg font-semibold text-foreground">Inbox Concierge</h1>
          <p className="text-sm text-muted-foreground">
            Connect your Gmail account to get your inbox triaged automatically.
          </p>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <a href={api.loginUrl()}>Sign in with Google</a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
