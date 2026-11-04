/** C-7 errors. */
import { HttpException, HttpStatus } from "@nestjs/common";

import { MESSAGES, type Message } from "./messages.js";

export class FieldErrors extends HttpException {
  constructor(fields: Record<string, Message>) {
    super({ fields }, HttpStatus.BAD_REQUEST);
  }
}

export class Conflict extends HttpException {
  constructor(reason: Message, extra: Record<string, unknown> = {}) {
    super({ reason, ...extra }, HttpStatus.CONFLICT);
  }
}

export class Forbidden extends HttpException {
  constructor(reason?: Message) {
    super(reason ? { reason } : { error: "forbidden" }, HttpStatus.FORBIDDEN);
  }
}

export class NotFound extends HttpException {
  constructor() {
    super({ error: "not_found" }, HttpStatus.NOT_FOUND);
  }
}

export class Unauthorized extends HttpException {
  constructor(reason?: Message) {
    super(reason ? { reason } : { error: "unauthorized" }, HttpStatus.UNAUTHORIZED);
  }
}

export class BadQuery extends HttpException {
  constructor(what: string) {
    super({ error: "bad_query", what }, HttpStatus.BAD_REQUEST);
  }
}

export { MESSAGES };
