import { Hono } from "hono";
import type { Env, JWTPayload } from "../types";
import { authMiddleware, adminMiddleware } from "../middleware/auth";
import { getUserById, updateUser, listUsers, toProfile } from "../services/user.service";

type UserEnv = { Bindings: Env; Variables: { user: JWTPayload } };

const users = new Hono<UserEnv>();

// All routes require auth
users.use("/*", authMiddleware);

/** GET /users/me — get current user profile */
users.get("/me", async (c) => {
  const userId = c.get("user").sub;
  const user = await getUserById(c.env, userId);

  if (!user) {
    return c.json({ error: "User not found" }, 404);
  }

  return c.json(toProfile(user));
});

/** PATCH /users/me — update current user profile */
users.patch("/me", async (c) => {
  const userId = c.get("user").sub;
  const body = await c.req.json<{ displayName?: string }>();

  const user = await updateUser(c.env, userId, body);
  if (!user) {
    return c.json({ error: "User not found" }, 404);
  }

  return c.json(toProfile(user));
});

/** GET /users — list all users (admin only) */
users.get("/", adminMiddleware, async (c) => {
  const profiles = await listUsers(c.env);
  return c.json({ users: profiles });
});

export default users;
