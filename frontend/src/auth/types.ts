export type AuthUser = {
  id: string;
  username: string;
  display_name: string;
  must_change_password: boolean;
  permissions: string[];
  roles?: string[];
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthUser;
};

export type LoginValues = {
  username: string;
  password: string;
  remember_me: boolean;
};
