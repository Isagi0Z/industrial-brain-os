import { Page, Locator } from '@playwright/test';
import * as human from '../utils/human';

export class LoginPage {
  constructor(private readonly page: Page) {}
  async goto(): Promise<void> {
    await this.page.goto('/login');
  }
  email(): Locator {
    return this.page.locator('#email');
  }
  password(): Locator {
    return this.page.locator('#password');
  }
  submit(): Locator {
    return this.page.getByRole('button', { name: /sign in/i });
  }
  error(): Locator {
    return this.page.getByRole('alert');
  }
  signupLink(): Locator {
    return this.page.getByRole('link', { name: /sign up/i });
  }
  async login(email: string, password: string): Promise<void> {
    await human.type(this.page, this.email(), email);
    await human.type(this.page, this.password(), password);
    await human.click(this.page, this.submit());
  }
}

export class SignupPage {
  constructor(private readonly page: Page) {}
  async goto(): Promise<void> {
    await this.page.goto('/signup');
  }
  fullName(): Locator {
    return this.page.locator('#full-name');
  }
  email(): Locator {
    return this.page.locator('#signup-email');
  }
  password(): Locator {
    return this.page.locator('#signup-password');
  }
  submit(): Locator {
    return this.page.getByRole('button', { name: /sign up/i });
  }
  error(): Locator {
    return this.page.getByRole('alert');
  }
  signinLink(): Locator {
    return this.page.getByRole('link', { name: /sign in/i });
  }
}
