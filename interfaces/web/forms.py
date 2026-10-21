from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

Usuario = get_user_model()

_INPUT = (
    "w-full rounded-xl bg-white/[0.04] border border-white/10 px-4 py-3 text-sm text-white "
    "placeholder-zinc-500 focus:border-volt/50 focus:bg-white/[0.07] focus:ring-4 "
    "focus:ring-volt/15 outline-none transition"
)


class RegistroForm(UserCreationForm):
    """Registro de compradores. El correo es obligatorio: ahí llegan las entradas."""

    email = forms.EmailField(label=_("Correo electrónico"), required=True)

    class Meta:
        model = Usuario
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": _("Elige un usuario"),
            "email": "tu@correo.com",
            "password1": _("Mínimo 8 caracteres"),
            "password2": _("Repite la contraseña"),
        }
        for nombre, campo in self.fields.items():
            campo.widget.attrs.update(
                {"class": _INPUT, "placeholder": str(placeholders.get(nombre, ""))}
            )
        self.fields["username"].help_text = ""
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Ya existe una cuenta con este correo."))
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data["email"]
        # Cuenta de comprador común: jamás staff ni superusuario.
        usuario.is_staff = False
        usuario.is_superuser = False
        if commit:
            usuario.save()
        return usuario
